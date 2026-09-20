"""Bounded state history. Pixel masters remain immutable and are not copied."""
import copy


class History:
    def __init__(self, state, limit=60):
        self.limit=limit;self.reset(state)
    def reset(self,state):
        self.states=[copy.deepcopy(state)];self.index=0
    def record(self,state):
        if self.states[self.index]==state:return
        del self.states[self.index+1:]
        self.states.append(copy.deepcopy(state))
        if len(self.states)>self.limit:self.states.pop(0)
        self.index=len(self.states)-1
    def move(self,delta):
        target=self.index+delta
        if 0<=target<len(self.states):
            self.index=target;return copy.deepcopy(self.states[target])
        return None
