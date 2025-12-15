async function loadJson(path){
  const res = await fetch(path, {cache: "no-store"});
  if(!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function renderWordcloud(items){
  const canvas = document.getElementById("wc");
  const list = (items || []).slice(0, 120).map(x => [x.term, x.count]);
  if(!list.length){
    const ctx = canvas.getContext("2d");
    ctx.clearRect(0,0,canvas.width,canvas.height);
    ctx.fillText("No data yet. Run GitHub Action.", 10, 30);
    return;
  }
  WordCloud(canvas, {
    list,
    gridSize: 10,
    weightFactor: (size) => Math.max(12, Math.log(size + 1) * 22),
    rotateRatio: 0.15,
    rotationSteps: 2,
    backgroundColor: "transparent",
  });
}

function renderSentimentChart(summary){
  const hist = summary.sentiment_histogram || {};
  const labels = ["1", "2", "3", "4", "5"];
  const values = labels.map(k => Number(hist[k] || 0));

  const ctx = document.getElementById("sentChart").getContext("2d");
  new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [{label: "Post count", data: values}]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {beginAtZero: true}
      }
    }
  });
}

function renderTopItems(summary){
  const box = document.getElementById("topItems");
  box.innerHTML = "";
  const top = (summary.top_requested_items || []).slice(0, 24);
  for(const x of top){
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.textContent = `${x.term} · ${x.count}`;
    box.appendChild(chip);
  }
}

async function main(){
  try{
    const [summary, wordfreq] = await Promise.all([
      loadJson("../data/summary.json"),
      loadJson("../data/wordfreq.json"),
    ]);
    renderWordcloud(wordfreq);
    renderSentimentChart(summary);
    renderTopItems(summary);
  }catch(err){
    console.error(err);
    // leave blank
  }
}
main();
