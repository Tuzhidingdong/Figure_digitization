from collections import deque
class MCMF:
    def __init__(self,n): self.g=[[] for _ in range(n)]
    def add(self,u,v,cap,cost):
        self.g[u].append([v,len(self.g[v]),cap,cost]); self.g[v].append([u,len(self.g[u])-1,0,-cost])
    def solve(self,s,t):
        n=len(self.g);flow=0;cost=0
        while True:
            dist=[float('inf')]*n;dist[s]=0;pv=[-1]*n;pe=[-1]*n
            inq=[False]*n;q=deque([s]);inq[s]=True
            while q:
                u=q.popleft();inq[u]=False
                for idx,e in enumerate(self.g[u]):
                    if e[2]>0 and dist[u]+e[3]<dist[e[0]]-1e-12:
                        dist[e[0]]=dist[u]+e[3];pv[e[0]]=u;pe[e[0]]=idx
                        if not inq[e[0]]:q.append(e[0]);inq[e[0]]=True
            print('SPFA dist',dist,'pv',pv)
            if dist[t]==float('inf'):break
            d=float('inf');v=t
            while v!=s:d=min(d,self.g[pv[v]][pe[v]][2]);v=pv[v]
            v=t
            while v!=s:
                e=self.g[pv[v]][pe[v]];e[2]-=d;rev=self.g[v][e[1]];rev[2]+=d;v=pv[v]
            flow+=d;cost+=d*dist[t]
        return flow,cost
# 2 fragments, edge cost -27 (bonus applied)
S=0;T=5
mf=MCMF(6)
for i in range(2):
    IN=1+2*i;OUT=2+2*i
    mf.add(S,IN,1,0);mf.add(IN,OUT,1,0);mf.add(OUT,T,1,0)
mf.add(2,3,1,-27.0)
print('flow,cost',mf.solve(S,T))
for i in range(2):
    print('out',i,[e for e in mf.g[2+2*i]])
