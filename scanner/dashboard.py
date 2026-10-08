"""Static dashboard (docs/index.html) for GitHub Pages, rebuilt on every run."""
import json
import os
import time

from . import config as C
from . import journal, portfolio

TEMPLATE = r"""<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>MemeRadar</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Heebo:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#f6f7f5;--panel:#fff;--ink:#18201d;--ink2:#4a5550;--muted:#78837e;--line:#dde2df;--grid:#eceeec;
--sig:#00876a;--sigs:#d7eee7;--warm:#b86e2a;--warms:#f4e4d4;--bad:#b3372c;--bads:#f6dcd9;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#101513;--panel:#171e1b;--ink:#e7ece9;--ink2:#b3beb9;--muted:#85918c;--line:#2a3430;
--grid:#222b27;--sig:#14a386;--sigs:#16362e;--warm:#cc7a35;--warms:#3a2a1c;--bad:#ef7a6e;--bads:#3d201d;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 Heebo,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:20px 16px calc(40px + env(safe-area-inset-bottom))}
h1{font-size:26px;margin:0}h2{font-size:17px;margin:0 0 10px}.muted{color:var(--muted);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:16px 0}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.tile b{display:block;font-size:26px;font-variant-numeric:tabular-nums}.tile span{color:var(--ink2);font-size:13px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px;margin-top:14px}
.chart{direction:ltr;overflow-x:auto}svg text{font:11px "IBM Plex Mono",monospace;fill:var(--muted)}
table{border-collapse:collapse;width:100%;font-size:13.5px}th,td{padding:7px 8px;border-bottom:1px solid var(--grid);text-align:start;white-space:nowrap}
th{color:var(--muted);font-weight:500;font-size:12px}.tw{overflow-x:auto}.n{font-family:"IBM Plex Mono",monospace;direction:ltr;text-align:end}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;font-size:12px}.up{background:var(--sigs);color:var(--sig)}
.dn{background:var(--bads);color:var(--bad)}.nt{background:var(--grid);color:var(--muted)}.tk{font-family:"IBM Plex Mono",monospace;font-weight:500;direction:ltr;unicode-bidi:isolate}
.empty{color:var(--muted);padding:20px 0;text-align:center}
.gr{display:grid;grid-template-columns:minmax(90px,34%) 1fr;gap:2px 10px;align-items:center;padding:5px 0;border-bottom:1px solid var(--grid)}
.gl{font-size:13.5px;grid-row:span 2}.gb{height:10px;background:var(--grid);border-radius:4px;overflow:hidden}.gb i{display:block;height:100%;background:var(--sig);border-radius:4px}
.gv{font:12px "IBM Plex Mono",monospace;color:var(--ink2);direction:ltr;text-align:right}
.tabs{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0}.tabs button{font:inherit;font-size:13.5px;border:1px solid var(--line);background:var(--panel);color:var(--ink2);border-radius:99px;padding:4px 12px;cursor:pointer}
.tabs button[aria-pressed="true"]{background:var(--ink);color:var(--bg);border-color:var(--ink)}.tabs button:focus-visible{outline:2px solid var(--sig);outline-offset:2px}
.big{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;direction:ltr;display:inline-block}
.pos{color:var(--sig)}.neg{color:var(--bad)}h3{font-size:14.5px;margin:14px 0 6px}
.bar{height:6px;background:var(--grid);border-radius:4px;position:relative;min-width:90px;direction:ltr}.bar i{position:absolute;top:-3px;width:3px;height:12px;border-radius:2px;background:var(--ink)}
</style></head><body><div class="wrap">
<h1>📡 MemeRadar</h1><div class="muted" id="upd"></div>
<div class="tiles" id="tiles"></div>
<div class="card" id="book"><h2>📈 תיק וירטואלי</h2>
<div class="muted" id="bookRules"></div>
<div class="tabs" id="bookTabs" role="group" aria-label="איזה תיק להציג"></div>
<div style="display:flex;gap:22px;flex-wrap:wrap;align-items:flex-end"><div><div class="muted">רווח/הפסד כולל</div><span class="big" id="bookTotal"></span></div><div class="muted" id="bookSub" style="max-width:520px"></div></div>
<div class="tiles" id="bookTiles"></div>
<div class="chart" id="bookCurve"></div>
<h3>פוזיציות פתוחות</h3><div class="tw"><table id="bookOpen"></table></div>
<h3>נסגרו</h3><div class="tw"><table id="bookClosed"></table></div>
</div>
<div class="card"><h2>רווח/הפסד על נייר לפי כללי הניסוי</h2><div class="muted" id="rules"></div><div class="chart" id="pnl"></div></div>
<div class="card"><h2>מה עובד: +20% תוך 3 ימים לפי קבוצה</h2><div class="chart" id="groups"></div></div>
<div class="card"><h2>🔬 מסלול הניסוי: תנועות של 10%-20%</h2>
<div class="muted">מניות עם שיח מוגבר (פי 3 מהרגיל) שלא קיבלת עליהן הודעה. כל אחת נבדקת על הנייר עם שלושה כללים, אחרי עלות של <span id="midcost"></span>% לעסקה. מחפשים קבוצה שבה העסקה הממוצעת חיובית לאורך זמן.</div>
<div class="tw" id="mid"></div></div>
<div class="card"><h2>כל ההתראות</h2><div class="tw"><table id="alerts"></table></div></div>
<div class="card"><h2>מצב המקורות היום</h2><div id="health"></div></div>
<p class="muted">תוצאות על נייר, לא ייעוץ השקעות. עם מעט התראות המספרים רועשים מאוד.</p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id),NS="http://www.w3.org/2000/svg";
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e}
const pct=v=>v==null?"—":(v>0?"+":"")+v+"%",rate=v=>v==null?"—":v+"%";
$("upd").textContent="עודכן: "+new Date(D.updated*1000).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem"});
$("rules").textContent=`כניסה במחיר ההתראה, מימוש ב-+${D.rules.tp}%, סטופ ב-−${D.rules.sl}%, עד ${D.rules.days} ימים, עלות ${D.rules.cost}% לעסקה`;
const S=D.all,W=D.week;
[[S.n,"התראות מההתחלה"],[W.n,"התראות השבוע"],[pct(S.hit20),"הגיעו ל-+20% תוך 3 ימים"],[pct(S.dd15),"ירדו 15% תוך 3 ימים"],
 [S.sim_mean==null?"—":pct(S.sim_mean),"עסקת ניסוי ממוצעת"],[S.sim_total==null?"—":pct(S.sim_total),"סה״כ על נייר"]]
 .forEach(([v,l])=>{const d=document.createElement("div");d.className="tile";d.innerHTML=`<b>${v}</b><span>${l}</span>`;$("tiles").appendChild(d)});

(function(){const B=D.book||{},keys=Object.keys(B);if(!keys.length){$("book").hidden=true;return}
 const usd=v=>v==null?"—":(v<0?"−":v>0?"+":"")+"$"+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
 const cls=v=>v==null?"":v>0?"pos":v<0?"neg":"";
 const dt=t=>t?new Date(t*1000).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"}):"—";
 const R={target:"🎯 יעד",stop:"🛑 סטופ",time:"⏱️ זמן"};
 $("bookRules").textContent=`בכל אות "קונים" ב-$${D.book_usd.toLocaleString()} לפי כללי הניסוי: יוצאים ביעד או בסטופ, ולכל היותר אחרי ${D.rules.days} ימים. עלות מסחר מנוכה. מתחיל ב-${new Date(D.book_start).toLocaleDateString("he-IL")}, ומניה שכבר מוחזקת לא נקנית שוב. המחירים מתעדכנים בכל סריקה.`;
 let cur=keys[0];try{const s=localStorage.getItem("mr_book");if(s&&B[s])cur=s}catch(e){}
 function draw(){const b=B[cur],S=b.summary;
  $("bookTabs").innerHTML=keys.map(k=>`<button type="button" data-k="${k}" aria-pressed="${k===cur}">${B[k].label} (${B[k].summary.n})</button>`).join("");
  $("bookTabs").querySelectorAll("button").forEach(x=>x.onclick=()=>{cur=x.dataset.k;try{localStorage.setItem("mr_book",cur)}catch(e){}draw()});
  const T=$("bookTotal");T.textContent=usd(S.total);T.className="big "+cls(S.total);
  $("bookSub").textContent=S.n?`${S.n} השקעות של $${D.book_usd.toLocaleString()} (סה״כ $${S.invested.toLocaleString()}), כלומר ${S.total_pct>0?"+":""}${S.total_pct}% על הכסף שהושקע. כרגע בעבודה: $${S.at_work.toLocaleString()}.`:"עוד לא נכנסו לאף פוזיציה בתיק הזה. זה יקרה באות הבא שעומד בכללים.";
  $("bookTiles").innerHTML=[[usd(S.realized),"רווח ממומש (נסגרו)",cls(S.realized)],[usd(S.unrealized),"רווח על הנייר (פתוחות)",cls(S.unrealized)],[S.open,"פתוחות עכשיו",""],[S.win==null?"—":S.win+"%","מהסגורות הרוויחו",""],[`${S.targets} / ${S.stops} / ${S.timeouts}`,"🎯 יעד / 🛑 סטופ / ⏱️ זמן",""]]
   .map(([v,l,c])=>`<div class="tile"><b class="${c}" style="direction:ltr">${v}</b><span>${l}</span></div>`).join("");
  const host=$("bookCurve");host.innerHTML="";const c=b.curve;
  if(c.length<2){host.innerHTML='<div class="empty">הגרף יופיע אחרי שתי פוזיציות שנסגרו.</div>'}else{
   const W=Math.max(300,host.clientWidth||600),H=180,L=56,Rr=60,Tt=12,Bb=24,pts=[[c[0][0]-3600,0]].concat(c);
   const x0=pts[0][0],x1=pts[pts.length-1][0],ys=pts.map(p=>p[1]),y0=Math.min(0,...ys),y1=Math.max(0,...ys),pad=(y1-y0)*.12||50;
   const X=t=>L+(t-x0)/(x1-x0||1)*(W-L-Rr),Y=v=>Tt+(y1+pad-v)/(y1-y0+2*pad)*(H-Tt-Bb);
   const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%"},host);
   for(let i=0;i<=3;i++){const v=y0-pad+(y1-y0+2*pad)*i/3;el("line",{x1:L,x2:W-Rr,y1:Y(v),y2:Y(v),stroke:"var(--grid)"},svg);el("text",{x:L-6,y:Y(v)+4,"text-anchor":"end"},svg).textContent="$"+Math.round(v)}
   el("line",{x1:L,x2:W-Rr,y1:Y(0),y2:Y(0),stroke:"var(--muted)"},svg);
   el("path",{d:pts.map((p,i)=>(i?"H"+X(p[0])+"V":"M"+X(p[0])+",")+Y(p[1])).join(""),fill:"none",stroke:"var(--sig)","stroke-width":2},svg);
   const l=pts[pts.length-1];el("circle",{cx:X(l[0]),cy:Y(l[1]),r:4,fill:"var(--sig)"},svg);el("text",{x:X(l[0])+6,y:Y(l[1])+4,style:"fill:var(--ink)"},svg).textContent=usd(l[1]);}
  const op=b.positions.filter(p=>p.status!=="closed"),cl=b.positions.filter(p=>p.status==="closed");
  const rng=p=>{if(!p.now||!p.sl||!p.tp)return"";const f=Math.max(0,Math.min(1,(p.now-p.sl)/(p.tp-p.sl)));return `<div class="bar" title="סטופ ${p.sl} · יעד ${p.tp}"><i style="left:${(f*100).toFixed(0)}%"></i></div>`};
  $("bookOpen").innerHTML=op.length?"<tr><th>מניה</th><th>נכנסנו</th><th>מחיר כניסה</th><th>עכשיו</th><th>רווח/הפסד</th><th>סטופ (שמאל) ← → יעד (ימין)</th><th>נגמר ב-</th></tr>"+op.map(p=>`<tr><td class="tk">$${p.ticker}</td><td>${dt(p.t)}</td><td class="n">${p.entry}</td><td class="n">${p.now??"ממתין"}</td><td class="n ${cls(p.pnl)}">${usd(p.pnl)}</td><td>${rng(p)}</td><td>${dt(p.until)}</td></tr>`).join(""):'<tr><td class="empty">אין פוזיציות פתוחות כרגע.</td></tr>';
  $("bookClosed").innerHTML=cl.length?"<tr><th>מניה</th><th>נכנסנו</th><th>יצאנו</th><th>סיבה</th><th>כניסה</th><th>יציאה</th><th>רווח/הפסד</th></tr>"+cl.slice(0,60).map(p=>`<tr><td class="tk">$${p.ticker}</td><td>${dt(p.t)}</td><td>${dt(p.now_t)}</td><td>${R[p.reason]||""}</td><td class="n">${p.entry}</td><td class="n">${p.now}</td><td class="n ${cls(p.pnl)}">${usd(p.pnl)}</td></tr>`).join(""):'<tr><td class="empty">עוד אין פוזיציות שנסגרו.</td></tr>';
 }
 draw()})();
(function(){const pts=D.entries.filter(e=>e.out.sim!=null).sort((a,b)=>a.t-b.t);const host=$("pnl");
 if(pts.length<2){host.innerHTML='<div class="empty">עסקאות הניסוי נסגרות 3 ימים אחרי ההתראה. הגרף יופיע אחרי שתיים.</div>';return}
 let s=0;const c=pts.map(e=>[e.t,s+=e.out.sim*100]);const W=Math.max(300,host.clientWidth||600),H=220,L=44,R=58,T=14,B=26;
 const x0=c[0][0],x1=c[c.length-1][0]||x0+1,ys=c.map(p=>p[1]).concat([0]),y0=Math.min(...ys),y1=Math.max(...ys),pad=(y1-y0)*.1||5;
 const X=t=>L+(t-x0)/(x1-x0||1)*(W-L-R),Y=v=>T+(y1+pad-v)/(y1-y0+2*pad)*(H-T-B);
 const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%"},host);
 for(let i=0;i<=4;i++){const v=y0-pad+(y1-y0+2*pad)*i/4;el("line",{x1:L,x2:W-R,y1:Y(v),y2:Y(v),stroke:"var(--grid)"},svg);el("text",{x:L-6,y:Y(v)+4,"text-anchor":"end"},svg).textContent=v.toFixed(0)+"%"}
 el("line",{x1:L,x2:W-R,y1:Y(0),y2:Y(0),stroke:"var(--muted)"},svg);
 el("path",{d:c.map((p,i)=>(i?"L":"M")+X(p[0])+","+Y(p[1])).join(""),fill:"none",stroke:"var(--sig)","stroke-width":2},svg);
 const l=c[c.length-1];el("circle",{cx:X(l[0]),cy:Y(l[1]),r:4,fill:"var(--sig)"},svg);el("text",{x:X(l[0])+6,y:Y(l[1])+4,style:"fill:var(--ink)"},svg).textContent=pct(+l[1].toFixed(1));
 [x0,(x0+x1)/2,x1].forEach(t=>{const d=new Date(t*1000);el("text",{x:X(t),y:H-6,"text-anchor":"middle"},svg).textContent=d.getDate()+"."+(d.getMonth()+1)})})();
(function(){const g=Object.entries(D.groups).filter(([k,v])=>v.evaluated>0);const host=$("groups");
 if(!g.length){host.innerHTML='<div class="empty">עוד אין התראות עם תוצאה.</div>';return}
 host.style.direction="rtl";host.innerHTML=g.map(([k,v])=>`<div class="gr"><span class="gl">${k}</span><span class="gb"><i style="width:${v.hit20||0}%"></i></span><span class="gv">${v.hit20??0}% · n=${v.evaluated}${v.sim_mean==null?"":" · ניסוי "+pct(v.sim_mean)}</span></div>`).join("")})();
(function(){const t=$("alerts");const rows=D.entries.slice().sort((a,b)=>b.t-a.t);
 if(!rows.length){t.outerHTML='<div class="empty">עוד לא נשלחו התראות. זה תקין: הסורק מתריע רק כשמשהו חריג.</div>';return}
 t.innerHTML="<tr><th>מתי</th><th>מניה</th><th>רמה</th><th>ציון</th><th>מקורות</th><th>מחיר</th><th>יום</th><th>3 ימים</th><th>שיא 3י</th><th>שפל 3י</th><th>ניסוי</th><th>שלך</th></tr>"+
 rows.map(e=>{const o=e.out,p=v=>v==null?'<span class="pill nt">…</span>':`<span class="pill ${v>=0?"up":"dn"}">${pct(+(v*100).toFixed(1))}</span>`;
  return `<tr><td>${new Date(e.t*1000).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"})}</td>
  <td class="tk">$${e.ticker}</td><td>${e.tier==="EARLY"?"🟢":"🟠"}</td><td class="n">${e.score??""}</td><td>${(e.sources||[]).join(" + ")}</td>
  <td class="n">${e.price??""}</td><td>${p(o.r1d)}</td><td>${p(o.r3d)}</td><td>${p(o.max3d)}</td><td>${p(o.min3d)}</td><td>${p(o.sim)}</td>
  <td>${e.fb==null?"":e.fb>0?"👍":"👎"}</td></tr>`}).join("")})();
$("midcost").textContent=D.mid_cost;
(function(){const host=$("mid"),M=D.mid||{},ks=Object.keys(M);
 if(!ks.length||!M[ks[0]].n){host.innerHTML='<div class="empty">עוד לא נרשמו מניות במסלול.</div>';return}
 const rk=Object.keys(M[ks[0]].rules);
 let h="<table><tr><th>קבוצה</th><th>נרשמו</th><th>עם תוצאה</th><th>הגיעו ל-+10%</th><th>ל-+20%</th><th>ירדו 10%</th>"+
  rk.map(k=>`<th>${M[ks[0]].rules[k].label}</th>`).join("")+"</tr>";
 const cell=r=>r.mean==null?'<span class="pill nt">…</span>':`<span class="pill ${r.mean>=0?"up":"dn"}">${pct(r.mean)}</span> <span class="muted">n=${r.n}</span>`;
 ks.forEach(k=>{const v=M[k];h+=`<tr><td>${k}</td><td class="n">${v.n}</td><td class="n">${v.evaluated}</td><td class="n">${rate(v.hit10)}</td><td class="n">${rate(v.hit20)}</td><td class="n">${rate(v.dd10)}</td>`+
  rk.map(r=>`<td>${cell(v.rules[r])}</td>`).join("")+"</tr>"});
 host.innerHTML=h+"</table>"})();
(function(){const h=D.health||{};const k=Object.keys(h);$("health").innerHTML=k.length?k.sort().map(n=>{const [ok,bad]=h[n];
 return `<div>${bad===0?"✅":ok?"⚠️":"❌"} ${n}: ${ok}/${ok+bad} הצליחו</div>`}).join(""):'<div class="muted">אין עדיין נתונים להיום</div>'})();
</script></body></html>
"""


def build(jr, state, now=None, path=None):
    now = now or int(time.time())
    path = path or C.DASHBOARD_PATH
    main_e = journal.main_entries(jr["entries"])
    week = [e for e in main_e if now - e["t"] < 7 * 86400]
    data = {
        "updated": now, "all": journal.stats(main_e), "week": journal.stats(week),
        "groups": journal.breakdown(main_e), "entries": main_e[-300:],
        "book": portfolio.build(jr["entries"], now), "book_usd": C.BOOK_USD, "book_start": C.BOOK_START,
        "mid": journal.mid_breakdown(journal.mid_entries(jr["entries"])), "mid_cost": round(C.MID_COST * 100, 1),
        "health": (state.get("health") or {}).get("src", {}),
        "rules": {"tp": round(C.TP_PCT * 100), "sl": round(C.STOP_PCT * 100), "days": C.HOLD_DAYS,
                  "cost": round(C.TRADE_COST * 100, 2)},
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
