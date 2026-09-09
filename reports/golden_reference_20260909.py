"""独立参考实现——主脑用来对账 worker 产物，不入仓库。
刻意不 import 仓库里任何被审对象，只用 stdlib + 真实 DB/meta。"""
import sqlite3, json, datetime
from decimal import Decimal, localcontext

REPO = '/opt/lpbot/lp-bot-v3-origin-check'
POOL = '0x52e65b17fb6e5ba00ed806f37afcd2daa50271ca'
Q128 = Decimal(2) ** 128

def load(n=200):
    meta = json.load(open(f'{REPO}/reports/lp_rh/pool_meta.json'))
    c = sqlite3.connect(f'{REPO}/reports/lp_rh/scanner.db')
    rows = list(c.execute(
        "SELECT sample_time, fee_growth_global_0, fee_growth_global_1, reference_mid FROM ("
        "SELECT * FROM rh_market_states WHERE asset_address=? ORDER BY sample_time DESC LIMIT ?"
        ") ORDER BY sample_time", (POOL, n)))
    return meta, rows

def inventory(position_usd, entry_price, range_pct, dec0, dec1, quote):
    """V3 区间仓位的初始两腿 + liquidity。返回 human 与 raw。"""
    with localcontext() as ctx:
        ctx.prec = 50
        P, rp = Decimal(str(entry_price)), Decimal(str(range_pct))
        sP, sA, sB = P.sqrt(), (P*(1-rp/100)).sqrt(), (P*(1+rp/100)).sqrt()
        u0, u1 = (sB-sP)/(sP*sB), sP-sA            # L=1 时的两腿
        L = Decimal(str(position_usd)) / (u0*P*quote + u1*quote)
        a0, a1 = L*u0, L*u1
        return {'L_human': +L, 'L_raw': +(L*Decimal(10)**((dec0+dec1)//2)),
                'amount0_human': +a0, 'amount1_human': +a1,
                'amount0_raw': +(a0*Decimal(10)**dec0), 'amount1_raw': +(a1*Decimal(10)**dec1),
                'reconstructed_usd': +(a0*P*quote + a1*quote),
                'token0_usd_share': +(a0*P*quote/Decimal(str(position_usd)))}

def replay(position_usd=Decimal(1000), capital_usd=Decimal(10000), quote=Decimal(1)):
    meta, rows = load()
    dec0, dec1 = meta['dec0'], meta['dec1']
    inv = inventory(position_usd, meta['input_price_usd'], meta['range_pct'], dec0, dec1, quote)
    L = inv['L_raw']
    with localcontext() as ctx:
        ctx.prec = 50
        accrued, prev = Decimal(0), None
        navs, hodls = [], []          # (sample_time, value) —— 窗口对齐用
        for st, fg0, fg1, mid in rows:
            if mid is None:           # loader 跳过无价样本
                continue
            price = Decimal(str(mid))
            if fg0 is not None and fg1 is not None:
                cur = (Decimal(str(fg0)), Decimal(str(fg1)))
                if prev is not None:
                    d0, d1 = cur[0]-prev[0], cur[1]-prev[1]
                    tok0 = L*d0/Q128/Decimal(10)**dec0
                    tok1 = L*d1/Q128/Decimal(10)**dec1
                    accrued += tok0*price*quote + tok1*quote
                prev = cur
                navs.append((st, capital_usd - position_usd + position_usd + accrued))
            hodls.append((st, inv['amount0_human']*price*quote + inv['amount1_human']*quote))
        return meta, inv, navs, hodls

def report():
    meta, inv, navs, hodls = replay()
    print("=== V3 初始两腿（position_usd=1000）===")
    for k in ('L_raw','amount0_raw','amount1_raw','token0_usd_share','reconstructed_usd'):
        print(f"  {k:20s} {inv[k]}")
    print(f"\n=== 回放（{len(navs)} 个有 NAV 的步 / {len(hodls)} 个有 HODL 的步）===")
    t0 = datetime.datetime.fromisoformat(navs[0][0].replace('Z','+00:00'))
    t1 = datetime.datetime.fromisoformat(navs[-1][0].replace('Z','+00:00'))
    secs = Decimal(str((t1-t0).total_seconds()))
    net = navs[-1][1] - navs[0][1]
    print(f"  窗口          {navs[0][0]} -> {navs[-1][0]}  ({secs}s)")
    print(f"  nav_start     {navs[0][1]}")
    print(f"  nav_end       {navs[-1][1]}")
    print(f"  net_pnl       {net}")
    print(f"  隐含年化 %    {net/Decimal(1000)*Decimal(365*24*3600)/secs*100}")
    print(f"  meta fee_apr  {meta['fee_apr_pct']}   <- 独立对照，应同数量级")
    # 窗口对齐的 hodl：只取与 nav 首尾同一 sample_time 的 hodl
    hd = dict(hodls)
    a, b = hd.get(navs[0][0]), hd.get(navs[-1][0])
    print(f"\n  hodl@nav_start {a}")
    print(f"  hodl@nav_end   {b}")
    print(f"  hodl_delta(对齐) {b-a if a and b else 'N/A'}")
    print(f"  hodl_delta(未对齐,现行口径) {hodls[-1][1]-hodls[0][1]}")
    print(f"  两者是否相等: {(b-a) == (hodls[-1][1]-hodls[0][1]) if a and b else 'N/A'}")

if __name__ == '__main__':
    report()

def position_value_at(price, L_human, entry_price, range_pct, quote):
    """V3 仓位在价格 price 时的市值（两腿数量随价格变化——这正是无常损失的来源）。"""
    with localcontext() as ctx:
        ctx.prec = 50
        P, E, rp = Decimal(str(price)), Decimal(str(entry_price)), Decimal(str(range_pct))
        sA, sB = (E*(1-rp/100)).sqrt(), (E*(1+rp/100)).sqrt()
        sP = P.sqrt()
        if sP <= sA:      a0, a1 = L_human*(sB-sA)/(sA*sB), Decimal(0)   # 全 token0
        elif sP >= sB:    a0, a1 = Decimal(0), L_human*(sB-sA)           # 全 token1
        else:             a0, a1 = L_human*(sB-sP)/(sP*sB), L_human*(sP-sA)
        return +(a0*P*quote + a1*quote), +a0, +a1

def il_report():
    meta, inv, navs, hodls = replay()
    _, rows = load()
    quote = Decimal(1)
    p_start = next(Decimal(str(r[3])) for r in rows if r[3] is not None)
    p_end   = [Decimal(str(r[3])) for r in rows if r[3] is not None][-1]
    E, rp = meta['input_price_usd'], meta['range_pct']
    v0,_,_ = position_value_at(p_start, inv['L_human'], E, rp, quote)
    v1,a0,a1 = position_value_at(p_end,  inv['L_human'], E, rp, quote)
    h0 = inv['amount0_human']*p_start*quote + inv['amount1_human']*quote
    h1 = inv['amount0_human']*p_end*quote   + inv['amount1_human']*quote
    fees = navs[-1][1]-navs[0][1]
    print("\n=== LP 仓位市价重估 vs 现行「本金恒 1000」记账 ===")
    print(f"  价格         {p_start}  ->  {p_end}   ({(p_end/p_start-1)*100:.4f}%)")
    print(f"  LP 仓位市值   {v0}  ->  {v1}")
    print(f"  仓位价值变化  {v1-v0}")
    print(f"  hodl 同两腿   {h0}  ->  {h1}   (变化 {h1-h0})")
    print(f"  无常损失      {(v1-v0)-(h1-h0)}   <- LP 相对 hodl 的价格暴露差")
    print(f"  期间手续费    {fees}")
    print(f"\n  现行 NAV 口径  net_pnl = 手续费 = {fees}         （仓位价值变化被完全忽略）")
    print(f"  市价重估口径   net_pnl = 仓位变化 + 手续费 = {(v1-v0)+fees}")
    print(f"  两者相差       {(v1-v0)}   = {abs((v1-v0)/fees) if fees else 'inf'} 倍于手续费")
