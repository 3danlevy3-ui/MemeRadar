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
.now{display:grid;grid-template-columns:1.25fr 1fr;gap:14px;margin-top:14px}@media (max-width:760px){.now{grid-template-columns:1fr}}
.now .card{margin-top:0;min-width:0}.status{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.chip{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);background:var(--panel);border-radius:99px;padding:3px 11px;font-size:13px;color:var(--ink2)}
.hot{display:grid;gap:8px}.hrow{display:grid;grid-template-columns:auto 1fr auto;gap:2px 12px;align-items:center;padding:10px 12px;border:1px solid var(--line);border-radius:10px}
.hrow.pushed{border-color:var(--warm);background:var(--warms)}.fl{font-size:18px;letter-spacing:-3px;grid-row:span 2;min-width:3.2em;text-align:center}
.hrow .tk{font-size:16px}.hrow .why{color:var(--ink2);font-size:13px;grid-column:2/4}.hrow .chg{font:600 15px "IBM Plex Mono",monospace;direction:ltr}
.badge{font-size:11.5px;border-radius:99px;padding:1px 8px;background:var(--warm);color:#fff;margin-inline-start:6px;vertical-align:2px}
.hero{font-size:40px;font-weight:700;font-variant-numeric:tabular-nums;direction:ltr;display:inline-block;line-height:1.1}
.mini{display:grid;gap:6px;margin-top:10px}.mrow{display:flex;justify-content:space-between;gap:10px;font-size:14px;border-top:1px solid var(--grid);padding-top:6px}
.divider{margin:34px 0 4px;padding-top:16px;border-top:2px solid var(--line);font-size:20px}
</style></head><body><div class="wrap">
<h1>📡 MemeRadar</h1>
<div class="status" id="status"></div>
<div class="now">
 <div class="card"><h2>🔥 מה חם עכשיו</h2><div class="muted" style="margin:-6px 0 10px">מניות שהסורק ראה ב-6 השעות האחרונות. יותר להבות = שיח חזק יותר.</div><div class="hot" id="hot"></div></div>
 <div style="display:grid;gap:14px;align-content:start;min-width:0">
  <div class="card"><h2>💼 התיק: התראות לטלפון</h2><div class="muted">$1,000 לכל התראה, לפי כללי הניסוי</div>
   <div style="margin-top:8px"><span class="hero" id="heroPnl"></span></div><div class="muted" id="heroSub"></div>
   <div class="mini" id="heroOpen"></div></div>
  <div class="card"><h2>📲 התראות אחרונות</h2><div class="mini" id="lastPush" style="margin-top:0"></div></div>
 </div>
</div>
<div class="card" id="test"><h2>🧪 המבחן: האם הסורק עדיף על מזל?</h2>
<div class="muted" id="testIntro"></div><div class="tw" style="margin-top:8px"><table id="testTable"></table></div>
<div class="muted" id="testNote" style="margin-top:8px"></div></div>
<h2 class="divider">נתונים מלאים</h2>
<div class="muted">כל המספרים, הטבלאות וההיסטוריה. לא צריך לקרוא את זה כל יום.</div>
<div class="card"><h2>איכות האותות</h2><div class="muted">כל פעם שמניה נרשמה, כולל חזרות של אותה מניה</div><div class="tiles" id="tiles" style="margin-bottom:0"></div></div>
<div class="card" id="book"><h2>📈 תיק וירטואלי</h2>
<div class="muted" id="bookRules"></div>
<div class="tabs" id="bookTabs" role="group" aria-label="איזה תיק להציג"></div>
<div style="display:flex;gap:22px;flex-wrap:wrap;align-items:flex-end"><div><div class="muted">רווח/הפסד כולל</div><span class="big" id="bookTotal"></span></div><div class="muted" id="bookSub" style="max-width:520px"></div></div>
<div class="tiles" id="bookTiles"></div>
<h3>רווח/הפסד של התיק לאורך זמן (ממומש + על הנייר, בדולרים)</h3><div class="chart" id="bookCurve"></div>
<h3>פוזיציות פתוחות</h3><div class="tw"><table id="bookOpen"></table></div>
<h3>נסגרו</h3><div class="tw"><table id="bookClosed"></table></div>
</div>
<div class="card"><h2>מה עובד: +20% תוך 3 ימים לפי קבוצה</h2><div class="chart" id="groups"></div></div>
<div class="card"><h2>🔬 מסלול הניסוי: תנועות של 10%-20%</h2>
<div class="muted">מניות עם שיח מוגבר (פי 3 מהרגיל) שלא קיבלת עליהן הודעה. כל אחת נבדקת על הנייר עם שלושה כללים, אחרי עלות של <span id="midcost"></span>% לעסקה. מחפשים קבוצה שבה העסקה הממוצעת חיובית לאורך זמן.</div>
<div class="tw" id="mid"></div></div>
<div class="card"><h2>כל ההתראות</h2><div class="muted" style="margin:-4px 0 8px">חום: 🟢 מתחילה להתחמם · 🟠 חמה · 🔥 חמה מאוד</div><div class="tw"><table id="alerts"></table></div></div>
<div class="card"><h2>מצב המקורות היום</h2><div id="health"></div></div>
<p class="muted">תוצאות על נייר, לא ייעוץ השקעות. עם מעט התראות המספרים רועשים מאוד.</p>
</div>
<script>
const D=__DATA__;
const $=id=>document.getElementById(id),NS="http://www.w3.org/2000/svg";
function el(t,a,p){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);p&&p.appendChild(e);return e}
const pct=v=>v==null?"—":(v>0?"+":"")+v+"%",rate=v=>v==null?"—":v+"%";
const ago=t=>{const m=Math.max(0,Math.round((Date.now()/1000-t)/60));return m<1?"עכשיו":m<60?`לפני ${m} דק׳`:m<48*60?`לפני ${Math.round(m/60)} שע׳`:`לפני ${Math.round(m/1440)} ימים`};
const flames=sc=>sc>=70?"🔥🔥🔥":sc>=50?"🔥🔥":"🔥";
const heat=sc=>sc>=70?"🔥":sc>=50?"🟠":"🟢";
const money=v=>v==null?"—":(v<0?"−":v>0?"+":"")+"$"+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
(function(){const N=D.now||{},stale=Date.now()/1000-D.updated>45*60,bad=N.problems||[];
 const chips=[`<span class="chip">${stale?"⏸️ הסורק לא רץ":"🟢 הסורק פעיל"} · עודכן ${ago(D.updated)}</span>`,
  bad.length?`<span class="chip">⚠️ לא עובד כרגע: ${bad.join(", ")}</span>`:`<span class="chip">✅ כל המקורות עובדים</span>`,
  `<span class="chip">📲 ${N.pushes_24h||0} התראות לטלפון ב-24 שעות</span>`];
 $("status").innerHTML=chips.join("");
 const H=N.hot||[];
 $("hot").innerHTML=H.length?H.map(h=>{const chg=h.chg==null?"":`<span class="chg ${h.chg>=0?"pos":"neg"}">${h.chg>0?"+":""}${h.chg}%</span>`;
  return `<div class="hrow${h.pushed?" pushed":""}"><span class="fl" title="ציון ${h.score}">${flames(h.score)}</span>
  <span><span class="tk">$${h.ticker}</span>${h.pushed?'<span class="badge">קיבלת התראה</span>':""}</span>${chg}
  <span class="why">${h.why} · נראתה ${h.n} פעמים, לאחרונה ${ago(h.last)}</span></div>`}).join(""):'<div class="empty">שקט כרגע. אף מניה לא מתחממת ב-6 השעות האחרונות.</div>';
 const P=((D.book||{}).phone||{}),S0=P.summary||{};
 const hp=$("heroPnl");hp.textContent=money(S0.total);hp.className="hero "+(S0.total>0?"pos":S0.total<0?"neg":"");
 $("heroSub").textContent=S0.n?`על $${S0.invested.toLocaleString()} שהושקעו (${S0.total_pct>0?"+":""}${S0.total_pct}%) · ${S0.open} פתוחות${S0.waiting?`, ${S0.waiting} ממתינות לפתיחת המסחר`:""}, ${S0.closed} נסגרו`:"עוד לא נכנסו לאף עסקה.";
 const op=(P.positions||[]).filter(p=>p.status!=="closed");
 const others=Object.entries(D.book||{}).filter(([k])=>["all","mid","control","short_all","short_control"].includes(k)).map(([k,b])=>`<div class="mrow"><span class="muted">${b.label}</span><span class="n ${b.summary.total>0?"pos":b.summary.total<0?"neg":""}">${money(b.summary.total)}</span></div>`).join("");
 $("heroOpen").innerHTML=op.map(p=>p.status==="waiting"?`<div class="mrow"><span><span class="tk">$${p.ticker}</span> <span class="muted">⏳ ממתינה לפתיחת המסחר (תיקנה במחיר הפתיחה)</span></span><span class="n">—</span></div>`:`<div class="mrow"><span><span class="tk">$${p.ticker}</span> <span class="muted">פתוחה, נגמרת ${new Date(p.until*1000).toLocaleDateString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric"})}</span></span><span class="n ${p.pnl>0?"pos":p.pnl<0?"neg":""}">${money(p.pnl)}</span></div>`).join("")+others;
 const L=N.last_push||[];
 $("lastPush").innerHTML=L.length?L.map(x=>`<div class="mrow"><span>${x.kind==="extreme"?"⚡":"📲"} <span class="tk">$${x.ticker}</span> <span class="muted">${ago(x.t)}</span></span><span class="n ${x.ret>0?"pos":x.ret<0?"neg":""}">${x.ret==null?"ממתין":(x.ret>0?"+":"")+(x.ret*100).toFixed(1)+"%"}</span></div>`).join(""):'<div class="empty" style="padding:8px 0">אין התראות ב-7 הימים האחרונים.</div>';
})();
const S=D.all,W=D.week;
const PB=((D.book||{}).phone||{}).summary||{},usd0=v=>v==null?"—":(v<0?"−":v>0?"+":"")+"$"+Math.abs(v).toLocaleString("en-US",{maximumFractionDigits:0});
[[S.n,"רישומים מההתחלה"],[W.n,"רישומים השבוע"],[rate(S.hit20),"הגיעו ל-+20% תוך 3 ימים"],[rate(S.dd15),"ירדו 15% תוך 3 ימים"]]
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
  $("bookTiles").innerHTML=[[usd(S.realized),"רווח ממומש (נסגרו)",cls(S.realized)],[usd(S.unrealized),"רווח על הנייר (פתוחות)",cls(S.unrealized)],[S.waiting?`${S.open} + ${S.waiting} ⏳`:S.open,S.waiting?"פתוחות + ממתינות לפתיחה":"פתוחות עכשיו",""],[S.win==null?"—":S.win+"%","מהסגורות הרוויחו",""],[`${S.targets} / ${S.stops} / ${S.timeouts}`,"🎯 יעד / 🛑 סטופ / ⏱️ זמן",""]]
   .map(([v,l,c])=>`<div class="tile"><b class="${c}" style="direction:ltr">${v}</b><span>${l}</span></div>`).join("");
  const host=$("bookCurve");host.innerHTML="";
  const hist=((D.book_hist||{})[cur]||[]).map(p=>[p[0],p[1],p[2]]);
  const pts=hist.length>=2?hist:[];
  if(pts.length<2){host.innerHTML='<div class="empty">הגרף מתחיל להצטבר עכשיו: נקודה כל שעה, לפי השווי של התיק באותו רגע.</div>'}else{
   const W=Math.max(300,host.clientWidth||600),H=200,L=58,Rr=64,Tt=12,Bb=28;
   const x0=pts[0][0],x1=pts[pts.length-1][0],ys=pts.map(p=>p[1]),y0=Math.min(0,...ys),y1=Math.max(0,...ys),pad=(y1-y0)*.12||50;
   const X=t=>L+(t-x0)/(x1-x0||1)*(W-L-Rr),Y=v=>Tt+(y1+pad-v)/(y1-y0+2*pad)*(H-Tt-Bb);
   const svg=el("svg",{viewBox:`0 0 ${W} ${H}`,width:"100%",role:"img","aria-label":"רווח והפסד של התיק לאורך זמן"},host);
   for(let i=0;i<=3;i++){const v=y0-pad+(y1-y0+2*pad)*i/3;el("line",{x1:L,x2:W-Rr,y1:Y(v),y2:Y(v),stroke:"var(--grid)"},svg);el("text",{x:L-6,y:Y(v)+4,"text-anchor":"end"},svg).textContent=usd(Math.round(v))}
   el("line",{x1:L,x2:W-Rr,y1:Y(0),y2:Y(0),stroke:"var(--muted)"},svg);
   const area=pts.map((p,i)=>(i?"L":"M")+X(p[0])+","+Y(p[1])).join("")+`L${X(x1)},${Y(0)}L${X(x0)},${Y(0)}Z`;
   el("path",{d:area,fill:"var(--sigs)",opacity:.6},svg);
   el("path",{d:pts.map((p,i)=>(i?"L":"M")+X(p[0])+","+Y(p[1])).join(""),fill:"none",stroke:"var(--sig)","stroke-width":2},svg);
   const l=pts[pts.length-1];el("circle",{cx:X(l[0]),cy:Y(l[1]),r:4,fill:"var(--sig)"},svg);el("text",{x:X(l[0])+6,y:Y(l[1])+4,style:"fill:var(--ink)"},svg).textContent=usd(l[1]);
   const fmt=t=>new Date(t*1000).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"});
   const span=x1-x0,ticks=span>3*86400?4:3;
   for(let i=0;i<ticks;i++){const t=x0+span*i/(ticks-1);el("text",{x:X(t),y:H-8,"text-anchor":i===0?"start":i===ticks-1?"end":"middle"},svg).textContent=span>2*86400?new Date(t*1000).toLocaleDateString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric"}):fmt(t)}
   const tip=el("text",{x:L,y:Tt+2,style:"fill:var(--ink)"},svg),dot=el("circle",{r:4,fill:"var(--ink)",opacity:0},svg);
   svg.addEventListener("mousemove",ev=>{const r=svg.getBoundingClientRect(),xx=(ev.clientX-r.left)/r.width*W;let best=pts[0];for(const p of pts)if(Math.abs(X(p[0])-xx)<Math.abs(X(best[0])-xx))best=p;
    dot.setAttribute("cx",X(best[0]));dot.setAttribute("cy",Y(best[1]));dot.setAttribute("opacity",1);tip.textContent=`${fmt(best[0])} · ${usd(best[1])} · הושקעו $${(best[2]||0).toLocaleString()}`});
   svg.addEventListener("mouseleave",()=>{dot.setAttribute("opacity",0);tip.textContent=""});}
  const op=b.positions.filter(p=>p.status!=="closed"),cl=b.positions.filter(p=>p.status==="closed");
  const rng=p=>{if(!p.now||!p.sl||!p.tp)return"";const f=Math.max(0,Math.min(1,(p.now-p.sl)/(p.tp-p.sl)));return `<div class="bar" title="סטופ ${p.sl} · יעד ${p.tp}"><i style="left:${(f*100).toFixed(0)}%"></i></div>`};
  $("bookOpen").innerHTML=op.length?"<tr><th>מניה</th><th>נכנסנו</th><th>מחיר כניסה</th><th>עכשיו</th><th>רווח/הפסד</th><th>סטופ (שמאל) ← → יעד (ימין)</th><th>נגמר ב-</th></tr>"+op.map(p=>p.status==="waiting"?`<tr><td class="tk">$${p.ticker}</td><td colspan="6" class="muted">⏳ ההתראה הגיעה כשהשוק סגור (${dt(p.alert_t)}). נקנה במחיר הפתיחה של יום המסחר הבא.</td></tr>`:`<tr><td class="tk">$${p.ticker}</td><td>${dt(p.t)}</td><td class="n">${p.entry}</td><td class="n">${p.now??"ממתין"}</td><td class="n ${cls(p.pnl)}">${usd(p.pnl)}</td><td>${rng(p)}</td><td>${dt(p.until)}</td></tr>`).join(""):'<tr><td class="empty">אין פוזיציות פתוחות כרגע.</td></tr>';
  $("bookClosed").innerHTML=cl.length?"<tr><th>מניה</th><th>נכנסנו</th><th>יצאנו</th><th>סיבה</th><th>כניסה</th><th>יציאה</th><th>רווח/הפסד</th></tr>"+cl.slice(0,60).map(p=>`<tr><td class="tk">$${p.ticker}</td><td>${dt(p.t)}</td><td>${dt(p.now_t)}</td><td>${R[p.reason]||""}</td><td class="n">${p.entry}</td><td class="n">${p.now}</td><td class="n ${cls(p.pnl)}">${usd(p.pnl)}</td></tr>`).join(""):'<tr><td class="empty">עוד אין פוזיציות שנסגרו.</td></tr>';
 }
 draw()})();
(function(){const g=Object.entries(D.groups).filter(([k,v])=>v.evaluated>0);const host=$("groups");
 if(!g.length){host.innerHTML='<div class="empty">עוד אין התראות עם תוצאה.</div>';return}
 host.style.direction="rtl";host.innerHTML=g.map(([k,v])=>`<div class="gr"><span class="gl">${k}</span><span class="gb"><i style="width:${v.hit20||0}%"></i></span><span class="gv">${v.hit20??0}% · n=${v.evaluated}${v.sim_mean==null?"":" · ניסוי "+pct(v.sim_mean)}</span></div>`).join("")})();
(function(){const t=$("alerts");const rows=D.entries.slice().sort((a,b)=>b.t-a.t);
 if(!rows.length){t.outerHTML='<div class="empty">עוד לא נשלחו התראות. זה תקין: הסורק מתריע רק כשמשהו חריג.</div>';return}
 t.innerHTML="<tr><th>מתי</th><th>מניה</th><th>חום</th><th>ציון</th><th>מקורות</th><th>מחיר</th><th>יום</th><th>3 ימים</th><th>שיא 3י</th><th>שפל 3י</th><th>ניסוי</th><th>שלך</th></tr>"+
 rows.map(e=>{const o=e.out,p=v=>v==null?'<span class="pill nt">…</span>':`<span class="pill ${v>=0?"up":"dn"}">${pct(+(v*100).toFixed(1))}</span>`;
  return `<tr><td>${new Date(e.t*1000).toLocaleString("he-IL",{timeZone:"Asia/Jerusalem",day:"numeric",month:"numeric",hour:"2-digit",minute:"2-digit"})}</td>
  <td class="tk">$${e.ticker}</td><td title="ציון ${e.score??"—"}">${heat(e.score||0)}</td><td class="n">${e.score??""}</td><td>${(e.sources||[]).join(" + ")}</td>
  <td class="n">${e.price??""}</td><td>${p(o.r1d)}</td><td>${p(o.r3d)}</td><td>${p(o.max3d)}</td><td>${p(o.min3d)}</td><td>${p(o.sim)}</td>
  <td>${e.fb==null?"":e.fb>0?"👍":"👎"}</td></tr>`}).join("")})();
$("midcost").textContent=D.mid_cost;
(function(){const T=D.test;if(!T){$("test").hidden=true;return}
 const dd=new Date(T.decision+"T00:00:00Z").toLocaleDateString("he-IL",{day:"numeric",month:"numeric",year:"numeric"});
 $("testIntro").textContent=`כל יום מסחר נרשמות ${T.per_day} מניות קטנות אקראיות, בלי שום סיגנל, ונבדקות באותם כללים בדיוק. אם ההתראות לא טובות מהן בבירור, הסורק לא מוצא משהו אמיתי. בשורות השורט: אותן מניות בכיוון ההפוך (מרוויחים כשהן יורדות), אחרי עלות השאלה של 1% לעסקה. נקודת ההחלטה: ${dd}.`;
 const B0=D.book||{},sb=k=>(B0[k]||{}).summary,none={evaluated:null,hit20:null,dd15:null,sim_mean:null};
 const avg=S=>S&&S.closed?{evaluated:S.closed,hit20:null,dd15:null,sim_mean:Math.round(S.realized/S.closed)/10}:none;
 const rows=[["📲 התראות לטלפון",T.phone,sb("phone")],["📋 כל האותות",T.all,sb("all")],["🎲 קבוצת ביקורת",T.control,sb("control")],
  ["📉 שורט על כל האותות",avg(sb("short_all")),sb("short_all")],["📉 שורט על קבוצת הביקורת",avg(sb("short_control")),sb("short_control")]];
 const per=S=>S&&S.n?Math.round(S.total/S.n):null;const r=v=>v==null?"—":v+"%";
 $("testTable").innerHTML="<tr><th>קבוצה</th><th>נבדקו</th><th>הגיעו ל-+20% תוך 3 ימים</th><th>ירדו 15% תוך 3 ימים</th><th>עסקה ממוצעת</th><th>תיק: $ לכל $1,000</th></tr>"+
  rows.map(([l,s,b])=>`<tr><td>${l}</td><td class="n">${s.evaluated??"—"}</td><td class="n">${r(s.hit20)}</td><td class="n">${r(s.dd15)}</td><td class="n ${s.sim_mean>0?"pos":s.sim_mean<0?"neg":""}">${s.sim_mean==null?"—":(s.sim_mean>0?"+":"")+s.sim_mean+"%"}</td><td class="n ${per(b)>0?"pos":per(b)<0?"neg":""}">${per(b)==null?"—":money(per(b))}</td></tr>`).join("");
 $("testNote").textContent=T.control.evaluated<30?`קבוצת הביקורת רק התחילה (${T.control.evaluated} עם תוצאה). צריך לפחות 30 כדי להשוות.`:"השוואה הוגנת: אותה תקופה, אותם כללי כניסה ויציאה.";
})();
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


def now_view(entries, state, now):
    """The 'right now' panel: what is hot in the last 6 hours, recent phone alerts, broken sources."""
    main = [e for e in journal.main_entries(entries)]
    hot = {}
    for e in sorted(main, key=lambda x: x["t"]):
        if now - e["t"] > 6 * 3600:
            continue
        t = e["ticker"]
        h = hot.setdefault(t, {"ticker": t, "n": 0, "first": e["t"], "score": 0, "pushed": False, "src": set(),
                               "flags": [], "p0": e.get("price")})
        h["n"] += 1
        h["last"] = e["t"]
        h["score"] = max(h["score"], e.get("score") or 0)
        h["pushed"] |= e.get("channel") in ("push", "extreme")
        h["src"] |= set(e.get("sources") or [])
        for f in e.get("flags") or []:
            f = f.split(":")[0]
            if f not in h["flags"]:
                h["flags"].append(f)
        h["p1"] = (e.get("pos") or {}).get("last") or e.get("price")
    rows = []
    for h in hot.values():
        why = " + ".join(sorted(h.pop("src"))) or "שיח"
        if h["flags"]:
            why += " · " + " · ".join(h["flags"][:2])
        p0, p1 = h.pop("p0"), h.pop("p1")
        h["chg"] = round((p1 / p0 - 1) * 100, 1) if p0 and p1 and p1 != p0 else None
        h["why"] = why
        h.pop("flags")
        rows.append(h)
    rows.sort(key=lambda h: (not h["pushed"], -h["score"], -h["last"]))
    start = portfolio._start()
    pushes = [e for e in main if e.get("channel") in ("push", "extreme") and now - e["t"] < 7 * 86400 and e["t"] >= start]
    last_push = [{"ticker": e["ticker"], "t": e["t"], "kind": e["channel"], "ret": (e.get("pos") or {}).get("ret")}
                 for e in sorted(pushes, key=lambda x: -x["t"])[:6]]
    src = (state.get("health") or {}).get("src", {})
    names = {"reddit": "Reddit", "stocktwits": "Stocktwits", "yahoo": "מחירים", "finra": "שורט", "nasdaq": "Nasdaq",
             "google_trends": "Google Trends", "x": "X"}
    problems = [names.get(k, k) for k, (ok, bad) in src.items() if k != "errors" and bad and not ok]
    return {"hot": rows[:8], "last_push": last_push, "problems": problems,
            "pushes_24h": sum(1 for e in pushes if now - e["t"] < 86400)}


def build(jr, state, now=None, path=None):
    now = now or int(time.time())
    path = path or C.DASHBOARD_PATH
    main_e = journal.main_entries(jr["entries"])
    week = [e for e in main_e if now - e["t"] < 7 * 86400]
    books = portfolio.build(jr["entries"], now)
    data = {
        "updated": now, "all": journal.stats(main_e), "week": journal.stats(week),
        "groups": journal.breakdown(main_e), "entries": main_e[-300:],
        "now": now_view(jr["entries"], state, now), "book": books, "book_hist": portfolio.record_history(books, now), "book_usd": C.BOOK_USD,
        "book_start": C.BOOK_START,
        "mid": journal.mid_breakdown(journal.mid_entries(jr["entries"])), "mid_cost": round(C.MID_COST * 100, 1),
        "test": {"phone": journal.stats([e for e in main_e if e.get("channel") in ("push", "extreme")]),
                 "all": journal.stats(main_e), "control": journal.stats(journal.control_entries(jr["entries"])),
                 "decision": C.DECISION_DATE, "per_day": C.CONTROL_PER_DAY},
        "health": (state.get("health") or {}).get("src", {}),
        "rules": {"tp": round(C.TP_PCT * 100), "sl": round(C.STOP_PCT * 100), "days": C.HOLD_DAYS,
                  "cost": round(C.TRADE_COST * 100, 2)},
    }
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
