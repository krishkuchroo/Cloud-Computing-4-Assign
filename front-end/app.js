// cc-photos frontend
// Calls API Gateway directly via fetch with x-api-key header.
// The generated APIGW SDK in ./sdk/ is included in the deployment per the
// spec; this app is small enough that raw fetch is clearer to read.

(function () {
  const cfg = window.CC_PHOTOS_CONFIG || {};
  const API = cfg.apiBaseUrl;
  const KEY = cfg.apiKey;
  const BUCKET = cfg.photosBucket;

  const $ = (id) => document.getElementById(id);
  const setStatus = (el, msg, kind = "") => {
    el.textContent = msg;
    el.className = "status" + (kind ? " " + kind : "");
  };

  function renderResults(results) {
    const grid = $("results");
    grid.innerHTML = "";
    if (!results.length) {
      grid.innerHTML = '<p style="color:#888">No photos matched.</p>';
      return;
    }
    for (const r of results) {
      const fig = document.createElement("figure");
      const img = document.createElement("img");
      img.src = r.url;
      img.alt = (r.labels || []).join(", ");
      img.loading = "lazy";
      const cap = document.createElement("figcaption");
      cap.textContent = (r.labels || []).join(", ");
      fig.appendChild(img);
      fig.appendChild(cap);
      grid.appendChild(fig);
    }
  }

  async function search(q) {
    const url = `${API}/search?q=${encodeURIComponent(q)}`;
    const r = await fetch(url, { headers: { "x-api-key": KEY } });
    if (!r.ok) throw new Error(`Search failed (${r.status})`);
    const data = await r.json();
    return data.results || [];
  }

  async function upload(file, customLabels) {
    // Path: PUT /photos/{bucket}/{key}
    const safeKey = encodeURIComponent(file.name);
    const url = `${API}/photos/${BUCKET}/${safeKey}`;
    const headers = {
      "x-api-key": KEY,
      "Content-Type": file.type || "application/octet-stream",
    };
    const trimmed = (customLabels || "").trim();
    if (trimmed) headers["x-amz-meta-customLabels"] = trimmed;
    const r = await fetch(url, { method: "PUT", headers, body: file });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`Upload failed (${r.status}): ${txt.slice(0, 200)}`);
    }
  }

  $("search-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("q").value.trim();
    if (!q) return;
    setStatus($("status-search"), "Searching...");
    try {
      const results = await search(q);
      setStatus($("status-search"), `${results.length} result${results.length === 1 ? "" : "s"}`, "ok");
      renderResults(results);
    } catch (err) {
      setStatus($("status-search"), err.message, "error");
    }
  });

  $("upload-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = $("file").files[0];
    if (!file) return;
    const labels = $("custom-labels").value;
    setStatus($("status-upload"), `Uploading ${file.name}...`);
    try {
      await upload(file, labels);
      setStatus($("status-upload"), `Uploaded ${file.name}. Indexing takes ~5s; then search.`, "ok");
      $("upload-form").reset();
    } catch (err) {
      setStatus($("status-upload"), err.message, "error");
    }
  });

  if (!API || !KEY || !BUCKET) {
    setStatus($("status-search"), "config.js missing or incomplete; see config.example.js", "error");
  }
})();
