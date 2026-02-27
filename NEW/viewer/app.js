const DATA_URL = "../output/data/movies.json";
const PAGE_SIZE = 30;

const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");
const searchInput = document.getElementById("searchInput");
const sortSelect = document.getElementById("sortSelect");
const reloadBtn = document.getElementById("reloadBtn");
const sentinel = document.getElementById("sentinel");
const cardTemplate = document.getElementById("cardTemplate");

let allMovies = [];
let filteredMovies = [];
let renderedCount = 0;
let isRendering = false;

function formatVotes(v) {
  return typeof v === "number" ? v.toLocaleString() : "N/A";
}

function makeCard(movie) {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  const posterLink = node.querySelector(".poster-link");
  const poster = node.querySelector(".poster");
  const title = node.querySelector(".title");
  const meta = node.querySelector(".meta");
  const stats = node.querySelector(".stats");
  const imdb = node.querySelector(".imdb-link");

  title.textContent = movie.title || "Untitled";
  meta.textContent = `${movie.year || "Unknown year"} | ${movie.runtime || "Runtime N/A"}`;
  stats.textContent = `Rating: ${movie.rating ?? "N/A"} | Votes: ${formatVotes(movie.votes)}`;

  imdb.href = movie.imdb_url || "#";

  if (movie.poster_url) {
    poster.dataset.src = movie.poster_url;
    poster.alt = `${movie.title || "Movie"} poster`;
    posterLink.href = movie.poster_url;
  } else {
    poster.alt = "No poster available";
    posterLink.href = movie.imdb_url || "#";
  }

  return node;
}

const imageObserver = new IntersectionObserver((entries, observer) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    const img = entry.target;
    const src = img.dataset.src;
    if (src) {
      img.src = src;
      delete img.dataset.src;
    }
    observer.unobserve(img);
  });
}, { rootMargin: "200px" });

function sortMovies(movies, mode) {
  const arr = [...movies];
  arr.sort((a, b) => {
    if (mode === "title_asc") return (a.title || "").localeCompare(b.title || "");
    if (mode === "year_desc") return (b.year || 0) - (a.year || 0);
    if (mode === "year_asc") return (a.year || 0) - (b.year || 0);
    if (mode === "rating_desc") return (b.rating || 0) - (a.rating || 0);
    if (mode === "votes_desc") return (b.votes || 0) - (a.votes || 0);
    return 0;
  });
  return arr;
}

function applyFilters(reset = true) {
  const term = searchInput.value.trim().toLowerCase();
  const mode = sortSelect.value;

  filteredMovies = allMovies.filter((m) => (m.title || "").toLowerCase().includes(term));
  filteredMovies = sortMovies(filteredMovies, mode);

  if (reset) {
    renderedCount = 0;
    grid.innerHTML = "";
  }

  renderNextPage();
  updateStatus();
}

function renderNextPage() {
  if (isRendering) return;
  if (renderedCount >= filteredMovies.length) return;

  isRendering = true;

  const fragment = document.createDocumentFragment();
  const next = Math.min(renderedCount + PAGE_SIZE, filteredMovies.length);

  for (let i = renderedCount; i < next; i += 1) {
    const card = makeCard(filteredMovies[i]);
    const img = card.querySelector("img.poster");
    if (img && img.dataset.src) imageObserver.observe(img);
    fragment.appendChild(card);
  }

  grid.appendChild(fragment);
  renderedCount = next;
  isRendering = false;
  updateStatus();
}

function updateStatus() {
  statusEl.textContent = `Showing ${renderedCount} of ${filteredMovies.length} movies`;
}

async function loadData() {
  statusEl.textContent = "Loading data...";
  try {
    const res = await fetch(DATA_URL, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    allMovies = await res.json();
    applyFilters(true);
  } catch (err) {
    statusEl.textContent = "Failed to load data. Run a local server and make sure output/data/movies.json exists.";
    console.error(err);
  }
}

const listObserver = new IntersectionObserver((entries) => {
  const hit = entries.some((e) => e.isIntersecting);
  if (hit) renderNextPage();
}, { rootMargin: "400px" });

listObserver.observe(sentinel);

searchInput.addEventListener("input", () => applyFilters(true));
sortSelect.addEventListener("change", () => applyFilters(true));
reloadBtn.addEventListener("click", loadData);

loadData();
