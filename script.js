document.getElementById("year").textContent = new Date().getFullYear();

const toggle = document.querySelector(".nav-toggle");
const nav = document.querySelector(".site-nav");

toggle.addEventListener("click", () => {
  const isOpen = nav.classList.toggle("open");
  toggle.setAttribute("aria-expanded", String(isOpen));
});

nav.querySelectorAll("a").forEach((link) => {
  link.addEventListener("click", () => {
    nav.classList.remove("open");
    toggle.setAttribute("aria-expanded", "false");
  });
});

function formatDate(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}.${m}.${day}`;
}

async function loadLatest() {
  const list = document.getElementById("latest-list");
  if (!list) return;

  try {
    const res = await fetch("data/latest.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const items = await res.json();

    if (!Array.isArray(items) || items.length === 0) {
      throw new Error("empty feed");
    }

    list.innerHTML = "";
    items.slice(0, 10).forEach((item) => {
      const li = document.createElement("li");

      const dateSpan = document.createElement("span");
      dateSpan.className = "latest-date";
      dateSpan.textContent = formatDate(item.pubDate);

      const a = document.createElement("a");
      a.href = item.link;
      a.target = "_blank";
      a.rel = "noopener";
      a.textContent = item.title;

      if (item.r18) {
        const mark = document.createElement("em");
        mark.className = "r18-mark";
        mark.textContent = "R18";
        a.appendChild(mark);
      }

      li.appendChild(dateSpan);
      li.appendChild(a);
      list.appendChild(li);
    });

    list.dataset.state = "loaded";
  } catch (err) {
    list.innerHTML = `<li class="latest-placeholder">最新情報の自動取得に失敗しました。<a href="https://note.com/swi0801/m/me98fd692c5c2" target="_blank" rel="noopener">noteで直接ご確認ください</a></li>`;
    list.dataset.state = "error";
  }
}

loadLatest();
