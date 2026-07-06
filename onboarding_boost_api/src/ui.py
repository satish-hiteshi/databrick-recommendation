"""ui.py — built-in single-file test page for UC8 boost (convenience; React app is the primary UI)."""

PAGE = r"""<!doctype html><html><head><meta charset="utf-8"><title>Onboarding Boost (UC8) — Live Test</title>
<style>
 body{font-family:system-ui,Segoe UI,Arial;max-width:860px;margin:24px auto;padding:0 16px;color:#16202e;background:#f4f7fb}
 h1{font-size:21px;color:#0f4c75} .row{margin:13px 0}
 input[type=text]{width:100%;padding:9px 12px;border:1px solid #c9d4e0;border-radius:8px;font-size:15px}
 .res button{margin:3px;padding:5px 9px;border:1px solid #b9c6d6;background:#fff;border-radius:14px;cursor:pointer;font-size:13px}
 .res button:hover{background:#eef4fb}
 .chip{display:inline-block;margin:3px;padding:4px 10px;background:#dbeafe;border-radius:14px;font-size:13px}
 .chip b{cursor:pointer;color:#b00;margin-left:6px}
 .ctrls{display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:13px;color:#444}
 .ctrls label{display:flex;gap:5px;align-items:center}
 .ctrls input{width:64px;padding:5px;border:1px solid #c9d4e0;border-radius:6px}
 #go{padding:10px 18px;background:#0f4c75;color:#fff;border:0;border-radius:8px;font-size:15px;cursor:pointer}
 .grp{margin-top:16px;border:1px solid #d6e2ee;border-radius:10px;background:#fff;overflow:hidden}
 .grp h3{margin:0;padding:10px 14px;background:#0f4c75;color:#fff;font-size:15px;display:flex;justify-content:space-between}
 .grp h3 small{font-weight:400;opacity:.85}
 .it{padding:10px 14px;border-top:1px solid #eef3f8}
 .it b{font-size:15px} .it .v{color:#0f4c75;font-size:12px;text-transform:uppercase;margin-left:6px}
 .it .why{color:#555;font-style:italic;margin:3px 0;font-size:13px}
 .it .m{font-size:12px;color:#666} .it .m span{margin-right:12px}
 .badge{background:#e76f51;color:#fff;border-radius:10px;padding:1px 8px;font-size:11px;margin-left:6px}
 .actions{margin-top:16px;display:flex;gap:10px}
 .confirm{padding:11px 20px;background:#2e7d32;color:#fff;border:0;border-radius:8px;font-size:15px;cursor:pointer}
 .skip{padding:11px 20px;background:#fff;border:1px solid #888;color:#444;border-radius:8px;font-size:15px;cursor:pointer}
 .note{color:#777;font-size:12px;margin-top:8px} .ok{color:#2e7d32;font-weight:600}
</style></head><body>
<h1>🚀 Onboarding Boost (UC8) — Live Test</h1>
<div class="row"><label>1) Follow some properties (your onboarding seeds):</label>
 <input type="text" id="q" placeholder="search a name… e.g. Fortnite, The Witcher, Elden Ring"><div class="res" id="res"></div></div>
<div class="row"><b>Following:</b> <span id="followed"><small>none yet</small></span></div>
<div class="row ctrls">
 <label>user_id <input type="text" id="uid" value="13"></label>
 <label>target/vertical <input type="text" id="tpv" value="5"></label>
 <label>total cap <input type="text" id="cap" value="30"></label>
 <label>gap threshold <input type="text" id="gth" value="3"></label>
 <label>richness floor <input type="text" id="rf" value="0.5"></label>
 <label><input type="checkbox" id="dbg"> debug</label>
</div>
<div class="row"><button id="go" onclick="getBoost()">Boost my feed ▶</button></div>
<div id="out"></div>
<script>
let followed=[],names={},last=[],sid="onb_"+Math.random().toString(36).slice(2);
const esc=s=>(s||"").replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]));
document.getElementById('q').oninput=function(){clearTimeout(window.t);window.t=setTimeout(doSearch,250)};
async function doSearch(){const q=document.getElementById('q').value;if(!q){res.innerHTML='';return}
 const d=await(await fetch('/onboarding/boost/search?q='+encodeURIComponent(q))).json();last=d;
 res.innerHTML=d.map((x,i)=>`<button onclick="pick(${i})">${esc(x.name)} <small>[${x.vertical}]</small></button>`).join('')||'<small>no match</small>';}
function pick(i){const x=last[i];names[x.property_id]=esc(x.name)+' ['+x.vertical+']';if(!followed.includes(x.property_id))followed.push(x.property_id);render();}
function rm(p){followed=followed.filter(x=>x!=p);render();}
function render(){followedEl.innerHTML=followed.length?followed.map(p=>`<span class="chip">${names[p]||p}<b onclick="rm(${p})">✕</b></span>`).join(''):'<small>none yet</small>';}
const res=document.getElementById('res'),followedEl=document.getElementById('followed'),out=document.getElementById('out');
async function getBoost(){
 const rec={session_id:sid,user_id:+document.getElementById('uid').value,followed_property_ids:followed,
  target_per_vertical:+document.getElementById('tpv').value,total_cap:+document.getElementById('cap').value,
  gap_threshold:+document.getElementById('gth').value,richness_floor:+document.getElementById('rf').value,
  debug:document.getElementById('dbg').checked};
 const d=(await(await fetch('/onboarding/boost',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({dataframe_records:[rec]})})).json()).predictions[0];
 const c=d.context;let h=`<div class="note">seeds: ${c.seed_count} · gaps: ${c.gap_verticals_detected.join(', ')||'none'} · suggesting ${c.total_suggested}</div>`;
 for(const g of d.boost_payload){
  if(!g.properties.length)continue;
  h+=`<div class="grp"><h3>${esc(g.vertical_label)} <small>${g.kind} · ${g.properties.length}</small></h3>`;
  for(const p of g.properties){
   h+=`<div class="it"><b>${esc(p.name)}</b><span class="v">${p.vertical}</span>${p.badge?`<span class="badge">${p.badge}</span>`:''}
    <div class="why">${esc(p.why_string)}</div>
    <div class="m"><span>score ${p.score}</span><span>moment richness ${p.moment_richness_score}</span>
     <span>popularity ${p.popularity_score}</span><span>moments ${p.moment_count}</span></div></div>`;}
  h+=`</div>`;}
 if(c.total_suggested>0) h+=`<div class="actions"><button class="confirm" onclick="conf('confirm')">✓ Confirm boost (${c.total_suggested})</button>
  <button class="skip" onclick="conf('skip')">Skip boost</button></div>`;
 if(d.debug) h+=`<pre class="note" style="white-space:pre-wrap">${esc(JSON.stringify(d.debug,null,1))}</pre>`;
 out.innerHTML=h;}
async function conf(action){
 const d=(await(await fetch('/onboarding/boost/confirm',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({dataframe_records:[{session_id:sid,user_id:+document.getElementById('uid').value,action}]})})).json()).predictions[0];
 if(action==='skip'){out.innerHTML+=`<div class="note ok">Boost skipped. Total follows now: ${d.total_followed_now}</div>`;return}
 out.innerHTML+=`<div class="note ok">✓ Wrote ${d.written} follows (${d.already_followed||0} already). Total follows now: ${d.total_followed_now}</div>`;}
render();
</script></body></html>"""
