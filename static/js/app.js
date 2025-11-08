const $ = (q) => document.querySelector(q);
const cards = $("#price-cards");
let chart;

async function j(url){const r=await fetch(url);return r.json();}
function fmt(n){return n>=1?n.toLocaleString(undefined,{maximumFractionDigits:2}):n.toLocaleString(undefined,{maximumFractionDigits:6});}
function col(v){return v>0?"limegreen":v<0?"salmon":"#93a2d6";}

async function loadPrices(){
  const ids = $("#coins").value.trim();
  const vs  = $("#vs").value.trim();
  const res = await j(`/api/crypto/price?ids=${encodeURIComponent(ids)}&vs=${encodeURIComponent(vs)}`);
  if(!res.ok){cards.innerHTML=`<div class="card">Error: ${res.error}</div>`;return;}
  cards.innerHTML="";
  Object.entries(res.data).forEach(([coin,obj])=>{
    const now=obj[vs], chg=obj[`${vs}_24h_change`];
    const el=document.createElement("div"); el.className="card";
    el.innerHTML = `
      <div class="title" style="font-weight:600">${coin}</div>
      <div class="price" style="font-size:22px">${vs.toUpperCase()} ${fmt(now)}</div>
      <div class="change" style="color:${col(chg)}">${(chg??0).toFixed(2)}% / 24h</div>
      <button data-c="${coin}">Show 7d</button>
    `;
    cards.appendChild(el);
    el.querySelector("button").addEventListener("click",()=>loadChart(coin,vs));
  });
}

async function loadChart(coin,vs){
  const res = await j(`/api/crypto/history?coin_id=${encodeURIComponent(coin)}&vs=${encodeURIComponent(vs)}&days=7`);
  if(!res.ok) return alert(res.error);
  const pts = res.data?.prices || [];
  const labels = pts.map(p=>new Date(p[0]));
  const series = pts.map(p=>p[1]);
  const ctx = document.getElementById("priceChart").getContext("2d");
  if(chart) chart.destroy();
  $("#chart-title").innerText = `${coin} — last 7d (${vs.toUpperCase()})`;
  chart = new Chart(ctx,{
    type:"line",
    data:{labels,datasets:[{label:`${coin} (${vs})`,data:series,tension:0.25}]},
    options:{responsive:true,scales:{x:{type:"time",time:{unit:"day"}},y:{beginAtZero:false}}}
  });
}

$("#btn-refresh").addEventListener("click", loadPrices);

document.getElementById("add-form").addEventListener("submit", async (e)=>{
  e.preventDefault();
  const fd=new FormData(e.target);
  const body=Object.fromEntries(fd.entries());
  body.alert_enabled=!!fd.get("alert_enabled");
  if(body.target_price==="") delete body.target_price;

  await fetch("/api/watchlist",{
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify(body)
  });
  e.target.reset();
  renderWatchlist();
});

async function renderWatchlist(){
  const res = await j("/api/watchlist");
  if(!res.ok) return;
  const rows = res.data||[];
  const root=document.getElementById("watchlist-table");
  if(!rows.length){root.innerHTML="<p>No items yet.</p>"; return;}
  root.innerHTML=`<table><thead><tr><th>Name</th><th>Symbol</th><th>Target</th><th>Alert</th><th></th></tr></thead>
    <tbody>${rows.map(r=>`<tr>
      <td>${r.name}</td>
      <td>${r.symbol.toUpperCase()}</td>
      <td>${r.target_price??"-"}</td>
      <td>${r.alert_enabled?"On":"Off"}</td>
      <td><button data-del="${r.coin_id}">Delete</button></td>
    </tr>`).join("")}</tbody></table>`;
  root.querySelectorAll("button[data-del]").forEach(b=>b.addEventListener("click", async()=>{
    await fetch(`/api/watchlist/${encodeURIComponent(b.dataset.del)}`,{method:"DELETE"});
    renderWatchlist();
  }));
}

loadPrices();
renderWatchlist();
