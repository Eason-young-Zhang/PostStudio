"""Offline, deterministic Oklab palette analysis, independent of Qt and layout.

Oklab matrices: Björn Ottosson, https://bottosson.github.io/posts/oklab/
(public-domain reference, 2021 matrices). Input/output colors remain sRGB16.
"""
from __future__ import annotations
import numpy as np

ALGORITHM_VERSION=1
M1=np.array([[.4122214708,.5363325363,.0514459929],
             [.2119034982,.6806995451,.1073969566],
             [.0883024619,.2817188376,.6299787005]])
M2=np.array([[.2104542553,.7936177850,-.0040720468],
             [1.9779984951,-2.4285922050,.4505937099],
             [.0259040371,.7827717662,-.8086757660]])


def srgb_to_oklab(rgb):
    rgb=np.asarray(rgb,dtype=np.float64)
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    return np.cbrt(linear@M1.T)@M2.T


def oklab_to_srgb(lab):
    linear=((np.asarray(lab)@np.linalg.inv(M2).T)**3)@np.linalg.inv(M1).T
    return np.where(linear<=.0031308,12.92*linear,1.055*np.maximum(linear,0)**(1/2.4)-.055)


def rgb16(value):
    a=np.asarray(value)
    if a.shape!=(3,) or not np.all(np.isfinite(a)) or np.any(a<0) or np.any(a>65535):
        raise ValueError('色卡颜色必须是三个 0～65535 的通道值。')
    return np.rint(a).astype(np.uint16)


def hex_color(color):return '#'+''.join(f'{round(int(v)/257):02X}' for v in color)


def stratified_samples(pixels,limit=32768):
    """One seeded sample per equal-ish spatial tile; area and alpha weighted."""
    h,w=pixels.shape[:2]
    if h*w<=limit:
        values=pixels.reshape(-1,4);weights=values[:,3].astype(np.float64)/65535
    else:
        nx=min(w,max(1,int(np.sqrt(limit*w/h))));ny=min(h,max(1,limit//nx))
        xs=np.linspace(0,w,nx+1,dtype=int);ys=np.linspace(0,h,ny+1,dtype=int)
        rng=np.random.default_rng(20260917)
        x=xs[:-1][None,:]+(rng.random((ny,nx))*np.diff(xs)[None,:]).astype(int)
        y=ys[:-1][:,None]+(rng.random((ny,nx))*np.diff(ys)[:,None]).astype(int)
        values=pixels[y,x].reshape(-1,4)
        weights=(np.diff(ys)[:,None]*np.diff(xs)[None,:]).ravel()*values[:,3].astype(np.float64)/65535
    valid=weights>0
    return values[valid,:3].copy(),weights[valid]


def distances(points,centers):
    return np.sum((points[:,None,:]-centers[None,:,:])**2,axis=2)


class PaletteAnalysis:
    """Bounded sample cache; layout and ordering never trigger another pixel scan."""
    def __init__(self,pixels):
        self.rgb,self.weights=stratified_samples(pixels)
        if not len(self.rgb):raise ValueError('图像完全透明，没有可提取的颜色。')
        self.lab=srgb_to_oklab(self.rgb.astype(np.float64)/65535)
        # A coarse perceptual histogram supplies representative real pixels.
        bins=np.floor(self.lab*80).astype(np.int32)
        _,indices,inverse=np.unique(bins,axis=0,return_index=True,return_inverse=True)
        self.bin_weights=np.bincount(inverse,weights=self.weights)
        self.bin_lab=np.column_stack([np.bincount(inverse,weights=self.weights*self.lab[:,i])/self.bin_weights for i in range(3)])
        self.cache={};self.result_cache={}

    def extract(self,count=5,mode='area',locked=(),colors=()):
        count=int(count)
        if not 2<=count<=12:raise ValueError('颜色数量应为 2～12。')
        if mode not in ('area','distinctive'):raise ValueError('未知的配色提取方式。')
        locks=[rgb16(v).tolist() for v in locked]
        locks=list(dict.fromkeys(tuple(v) for v in locks))
        if len(locks)>count:raise ValueError('颜色数量不能少于已锁定的颜色数量。')
        explicit=[rgb16(v).tolist() for v in colors]
        if len(explicit)>count:raise ValueError('手动色卡超过指定颜色数量。')
        result_key=(count,mode,tuple(locks),tuple(tuple(v) for v in explicit))
        if result_key in self.result_cache:
            import copy
            return copy.deepcopy(self.result_cache[result_key])
        if explicit:
            explicit=list(dict.fromkeys(tuple(v) for v in explicit))
            if not set(locks).issubset(explicit):raise ValueError('手动色卡缺少已锁定颜色。')
            chosen=np.asarray(explicit,np.uint16)
        else:
            key=(count,mode,tuple(locks))
            if key not in self.cache:
                if len(self.cache)>=24:self.cache.pop(next(iter(self.cache)))
                self.cache[key]=self._cluster(count,mode,locks)
            chosen=self.cache[key]
        labels=np.argmin(distances(self.lab,srgb_to_oklab(chosen.astype(float)/65535)),axis=1)
        totals=np.bincount(labels,weights=self.weights,minlength=len(chosen));totals/=totals.sum()
        swatches=[dict(rgb16=c.tolist(),hex=hex_color(c),weight=float(weight),locked=tuple(c.tolist()) in locks) for c,weight in zip(chosen,totals)]
        result=dict(algorithm='oklab',algorithm_version=ALGORITHM_VERSION,requested_count=count,mode=mode,
                    sample_count=len(self.rgb),estimated=True,swatches=swatches,
                    note='有效颜色不足，已保留实际数量。' if len(chosen)<count else '')
        if len(self.result_cache)>=48:self.result_cache.pop(next(iter(self.result_cache)))
        self.result_cache[result_key]=result
        import copy
        return copy.deepcopy(result)

    def _cluster(self,count,mode,locks):
        points=self.bin_lab;mass=self.bin_weights.copy()
        if mode=='distinctive':mass=np.sqrt(mass) # Preserve rare, distinct chromatic groups.
        centers=list(srgb_to_oklab(np.asarray(locks,float)/65535)) if locks else []
        if not centers:centers=[points[np.argmax(mass)]]
        fixed=len(locks)
        if mode=='distinctive' and len(centers)<count:
            # Reserve one chromatically distinctive, non-negligible group. A plain
            # frequency-weighted centroid otherwise swallows small accent colors.
            d=distances(points,np.asarray(centers)).min(axis=1)
            fraction=self.bin_weights/self.bin_weights.sum()
            chroma=np.linalg.norm(points[:,1:],axis=1)
            delta=points[:,None,:]-np.asarray(centers)[None,:,:]
            accent_distance=(.15*delta[...,0]**2+np.sum(delta[...,1:]**2,axis=2)).min(axis=1)
            score=accent_distance*(chroma+.04)*fraction**.2
            score[fraction<.001]=0
            accent=int(np.argmax(score))
            if score[accent]>1e-9:centers.append(points[accent]);fixed=len(centers)
        while len(centers)<count:
            d=distances(points,np.asarray(centers)).min(axis=1)
            if d.max()<1e-8:break
            centers.append(points[np.argmax(d*mass)])
        centers=np.asarray(centers)
        for _ in range(16):
            labels=np.argmin(distances(points,centers),axis=1)
            updated=centers.copy()
            for i in range(fixed,len(centers)):
                mask=labels==i
                if mask.any():updated[i]=np.average(points[mask],weights=mass[mask],axis=0)
            if np.max(np.abs(updated-centers))<1e-5:break
            centers=updated
        chosen=[list(c) for c in locks]
        for center in centers[len(locks):]:
            nearest=int(np.argmin(np.sum((self.lab-center)**2,axis=1)))
            c=self.rgb[nearest].tolist()
            if c not in chosen:chosen.append(c)
        chosen=np.asarray(chosen,np.uint16)
        labels=np.argmin(distances(self.lab,srgb_to_oklab(chosen.astype(float)/65535)),axis=1)
        totals=np.bincount(labels,weights=self.weights,minlength=len(chosen))
        return chosen[np.argsort(-totals,kind='stable')]
