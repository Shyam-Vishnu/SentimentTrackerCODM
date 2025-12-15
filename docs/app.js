async function loadJson(path){
  const res = await fetch(path, {cache: "no-store"});
  if(!res.ok) throw new Error(`Failed to load ${path}`);
  return res.json();
}

function fmtDate(iso){
  try{
    const d = new Date(iso);
    return d.toLocaleString(undefined, {year:"numeric", month:"short", day:"2-digit", hour:"2-digit", minute:"2-digit"});
  }catch(e){
    return iso;
  }
}

function badgeClass(n){
  return `badge s${n}`;
}

function el(tag, attrs={}, children=[]){
  const e = document.createElement(tag);
  for(const [k,v] of Object.entries(attrs)){
    if(k === "class") e.className = v;
    else if(k === "html") e.innerHTML = v;
    else e.setAttribute(k, v);
  }
  for(const c of children){
    if(typeof c === "string") e.appendChild(document.createTextNode(c));
    else if(c) e.appendChild(c);
  }
  return e;
}

function renderSummary(summary){
  const box = document.getElementById("summary");
  box.innerHTML = "";
  const pills = [
    ["Subreddit", `r/${summary.subreddit}`],
    ["Posts", String(summary.post_count)],
    ["Avg sentiment", String(summary.avg_sentiment)],
    ["Generated", fmtDate(summary.generated_at_utc)],
  ];
  for(const [k,v] of pills){
    box.appendChild(el("div", {class:"pill"}, [el("b", {}, [k + ":"]), " " + v]));
  }
}

function renderPosts(posts){
  const container = document.getElementById("posts");
  container.innerHTML = "";
  if(!posts.length){
    container.appendChild(el("div", {class:"card"}, ["No posts found. Try adjusting MAX_AGE_HOURS or POST_LIMIT."]));
    return;
  }

  for(const p of posts){
    const meta = el("div", {class:"meta"}, [
      el("span", {class: badgeClass(p.sentiment_1_5)}, [String(p.sentiment_1_5)]),
      `by u/${p.author}`,
      `· ${fmtDate(p.created_iso)}`,
      `· ${p.num_comments} comments`,
      `· score ${p.score}`,
    ]);

    const titleLink = el("a", {href: p.permalink, target:"_blank", rel:"noreferrer"}, [p.title]);

    const tagWrap = el("div", {class:"tags"}, []);
    (p.requested_items || []).slice(0,5).forEach(t => tagWrap.appendChild(el("span", {class:"tag"}, [t])));

    const card = el("article", {class:"post"}, [
      el("h3", {}, [titleLink]),
      meta,
      el("p", {class:"reason"}, [p.sentiment_reason || ""]),
      el("p", {class:"preview"}, [(p.selftext || "").slice(0, 500)]),
      tagWrap
    ]);

    container.appendChild(card);
  }
}

async function main(){
  const subredditLine = document.getElementById("subredditLine");
  subredditLine.textContent = "Loading latest generated data…";
  try{
    const [summary, posts] = await Promise.all([
      loadJson("../data/summary.json"),
      loadJson("../data/posts.json")
    ]);
    subredditLine.textContent = `Tracking r/${summary.subreddit} · data updated ${fmtDate(summary.generated_at_utc)}`;
    renderSummary(summary);
    renderPosts(posts);
  }catch(err){
    subredditLine.textContent = "Could not load data yet. Run the GitHub Action once, then refresh.";
    console.error(err);
  }
}

document.getElementById("refreshBtn").addEventListener("click", () => main());
main();
