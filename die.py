D_TYPE = 6

print(f"combinations of two {D_TYPE}-dice")
l = []
for i in range(1,D_TYPE+1):
    for j in range(1,D_TYPE+1):
            l.append(i+j)
            #print(f"{i}+{j}={i+j}")

print("combination occurence")
r = {}
for i in range(min(l),max(l)+1):
    r[i] = [l.count(i)]
    #print(f"{i:>2} {r[i]}")


print("combination probability")
s = sum([v[0] for v in r.values()])
for k, v in r.items():
    r[k].append(v[0]/s)
    print(f"{k:>2} {v[0]/s*100:.3f}%")
