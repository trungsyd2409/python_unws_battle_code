import sys
lines=open(sys.argv[1]).read().split('\n')
W=H=0;edges={};tiles={};drag=[]
for l in lines:
    p=l.split()
    if not p: continue
    if p[0]=='MAP': W,H=int(p[1]),int(p[2])
    if p[0]=='EDGE': edges[int(p[1])]=(int(p[2]),int(p[3]))
    if p[0]=='TILE': tiles[(int(p[1]),int(p[2]))]=(int(p[3]),int(p[4]))
    if p[0]=='DRAGON':
        t=int(p[1]);n=int(p[2]);c=list(map(int,p[3:3+2*n]))
        drag.append((t,[(c[2*i],c[2*i+1]) for i in range(n)]))
R=W+1
def e(r,c):
    k=edges.get(r*R+c,(0,-1))
    return k
occ={}
for t,seg in drag:
    for i,(x,y) in enumerate(seg): occ[(x,y)]=('A' if t==0 else 'B') if i==0 else ('a' if t==0 else 'b')
out=[]
for y in range(H+1):
    s='+'
    for x in range(W):
        k=e(2*y,x); s+=('---' if k[0]==1 else ' P ' if k[0]==2 else '   ')+'+'
    out.append(s)
    if y==H: break
    s=''
    for x in range(W+1):
        k=e(2*y+1,x); s+=('|' if k[0]==1 else 'P' if k[0]==2 else ' ')
        if x<W:
            ch=occ.get((x,y))
            if ch is None: ch='.' if tiles.get((x,y),(0,0))[1]>0 else ' '
            s+=' '+ch+' '
    out.append(s)
print('\n'.join(out))
