async function main() {
  const meta = document.getElementById("meta");
  const jobsDiv = document.getElementById("jobs");

  try {
    const res = await fetch("../data/jobs.json");
    const data = await res.json();
    meta.textContent = `Updated: ${data.updated_at} | Matches: ${data.count}`;
    jobsDiv.innerHTML = "";

    for (const job of data.jobs || []) {
      const div = document.createElement("div");
      div.className = "job";
      const fitClass = job.fit === "good-fit" ? "good-fit" : "senior-not-fit";
      div.innerHTML = `
        <div><b>${job.source}</b></div>
        <div>${job.title}</div>
        <div class="fit ${fitClass}">${job.fit}</div>
        <small>Matched: ${(job.include_hits || []).join(", ") || "-"}</small><br/>
        <a href="${job.url}" target="_blank">Open notice</a>
      `;
      jobsDiv.appendChild(div);
    }
  } catch (e) {
    meta.textContent = "Could not load jobs.json";
  }
}
main();
