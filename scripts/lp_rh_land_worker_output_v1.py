"""带校验的 codex 产物落盘器。用法: land.py <out_file> [--min-lines N]
拒绝落盘的情况：标记之间内容为空、行数不足、或比现有文件缩水超过 50%。"""
import re, os, sys
REPO='/opt/lpbot/lp-bot-v3-origin-check'
def main():
    out=sys.argv[1]; minl=int(sys.argv[sys.argv.index('--min-lines')+1]) if '--min-lines' in sys.argv else 20
    raw=open(out).read()
    parts=re.split(r'^===FILE:(.+?)===$', raw, flags=re.M)
    lead=parts[0].strip()
    if lead: print(f"[前导说明]\n{lead[:600]}\n")
    if len(parts)<3: sys.exit("拒绝：没有找到任何 ===FILE: 标记")
    plan=[]
    for i in range(1,len(parts),2):
        path=parts[i].strip()
        body=re.sub(r'\n===END===\s*$','\n',parts[i+1]).lstrip('\n')
        n=len(body.splitlines())
        full=os.path.join(REPO,path)
        old=len(open(full).read().splitlines()) if os.path.exists(full) else 0
        if n < minl:
            sys.exit(f"拒绝：{path} 只有 {n} 行（< {minl}），worker 很可能没输出内容")
        if old and n < old*0.5:
            sys.exit(f"拒绝：{path} 从 {old} 行缩到 {n} 行（<50%），疑似截断")
        if not body.strip():
            sys.exit(f"拒绝：{path} 内容为空")
        plan.append((full,path,body,n,old))
    for full,path,body,n,old in plan:
        open(full,'w').write(body)
        print(f"落盘 {path}  {old} -> {n} 行")
if __name__=='__main__': main()
