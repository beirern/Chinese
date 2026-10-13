(() => {
  const list = document.querySelector("#word-list");
  if (!list) return;

  const rows = [...list.querySelectorAll(".word-row")];
  const search = document.querySelector("#word-search");
  const source = document.querySelector("#source-filter");
  const state = document.querySelector("#state-filter");
  const count = document.querySelector("#shown-count");
  const noResults = document.querySelector("#no-results");
  const pagination = document.querySelector("#word-pagination");
  const previous = document.querySelector("#previous-page");
  const next = document.querySelector("#next-page");
  const pageStatus = document.querySelector("#page-status");
  const pageSize = 18;
  let matches = rows;
  let page = 1;

  const searchable = value => value.toLocaleLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  rows.forEach(row => { row.dataset.search = searchable(row.dataset.search); });

  function showPage() {
    const totalPages = Math.max(1, Math.ceil(matches.length / pageSize));
    page = Math.min(Math.max(page, 1), totalPages);
    const start = (page - 1) * pageSize;
    const end = Math.min(start + pageSize, matches.length);
    rows.forEach(row => { row.hidden = true; });
    matches.slice(start, end).forEach(row => { row.hidden = false; });

    count.textContent = matches.length
      ? `Showing ${start + 1}–${end} of ${matches.length} ${matches.length === rows.length ? "words" : `matching words (${rows.length} total)`}`
      : `0 of ${rows.length} words`;
    noResults.hidden = matches.length !== 0;
    pagination.hidden = totalPages <= 1;
    pageStatus.textContent = `Page ${page} of ${totalPages}`;
    previous.disabled = page === 1;
    next.disabled = page === totalPages;
  }

  function filterWords() {
    const query = searchable(search.value.trim());
    matches = rows.filter(row =>
      (!query || row.dataset.search.includes(query)) &&
      (!source.value || row.dataset.sources.split(" ").includes(source.value)) &&
      (!state.value || row.dataset.state === state.value)
    );
    page = 1;
    showPage();
  }

  search.addEventListener("input", filterWords);
  source.addEventListener("change", filterWords);
  state.addEventListener("change", filterWords);
  previous.addEventListener("click", () => {
    page--;
    showPage();
    count.scrollIntoView({ block: "start" });
  });
  next.addEventListener("click", () => {
    page++;
    showPage();
    count.scrollIntoView({ block: "start" });
  });
  showPage();
})();
