const mockData = {
  selectedText:
    "Conhecer o inimigo e conhecer a si mesmo é a base de toda vitória.",
  card:
    "O texto se relaciona por **COMPLEMENTO** com Robert Greene, que amplia a ideia de conhecer o adversário pela observação e pela inteligência. Na pág. 44, a estratégia deixa de ser apenas preparação para se tornar leitura ativa das circunstâncias.",
  hits: [
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "44",
      score: 0.761,
      text: "…é a presciência da situação do inimigo.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "32",
      score: 0.743,
      text: "…esgote a força deles fazendo-os vir até você.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "30",
      score: 0.706,
      text: "…é sempre melhor fazer o seu adversário vir até você.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "51",
      score: 0.692,
      text: "…conheça o inimigo tão bem quanto conhece a si mesmo.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "67",
      score: 0.681,
      text: "…a informação é a chave para antecipar cada movimento.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "83",
      score: 0.664,
      text: "…observe os sinais antes de decidir qual será o próximo passo.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "101",
      score: 0.648,
      text: "…a aparência de segurança pode esconder a maior vulnerabilidade.",
    },
    {
      author: "Robert Greene",
      title: "As 48 leis do poder",
      page: "118",
      score: 0.631,
      text: "…quem domina a leitura da situação controla o ritmo do jogo.",
    },
  ],
};

const elements = {
  bookText: document.querySelector("#book-text"),
  selectionAction: document.querySelector("#selection-action"),
  connectSelection: document.querySelector("#connect-selection"),
  searchView: document.querySelector("#search-view"),
  connectionView: document.querySelector("#connection-view"),
  searchButton: document.querySelector("#search-button"),
  connections: document.querySelector("#connections"),
};

function appendFormattedText(container, text) {
  text.split("\n").forEach((line, lineIndex, lines) => {
    line.split("**").forEach((part, partIndex) => {
      if (partIndex % 2 === 1) {
        const strong = document.createElement("strong");
        strong.textContent = part;
        container.append(strong);
      } else {
        container.append(document.createTextNode(part));
      }
    });
    if (lineIndex < lines.length - 1) {
      container.append(document.createElement("br"));
    }
  });
}

function relationClass() {
  return "relation-badge";
}

function renderInvite() {
  elements.connectionView.innerHTML = `
    <div class="rail-invite">
      <span class="invite-mark">⌁</span>
      <p>Selecione um trecho para ver o que outros autores dizem.</p>
    </div>
  `;
}

function renderLoading() {
  elements.connectionView.innerHTML = `
    <div class="selected-snippet">
      <p class="eyebrow">Trecho consultado</p>
      <blockquote></blockquote>
    </div>
    <div class="rail-loading" aria-label="Procurando conexões">
      <p class="state-title">Procurando conexões...</p>
      <span class="skeleton-line"></span>
      <span class="skeleton-line"></span>
      <span class="skeleton-line short"></span>
    </div>
  `;
  elements.connectionView.querySelector("blockquote").textContent = mockData.selectedText;
}

function renderError() {
  elements.connectionView.innerHTML = `
    <div class="selected-snippet">
      <p class="eyebrow">Trecho consultado</p>
      <blockquote></blockquote>
    </div>
    <div class="rail-error">
      <p>Não foi possível buscar agora. Tente novamente.</p>
      <button class="retry-button" type="button">Tentar novamente</button>
    </div>
  `;
  elements.connectionView.querySelector("blockquote").textContent = mockData.selectedText;
  elements.connectionView.querySelector(".retry-button").addEventListener("click", runSearch);
}

function renderEvidence() {
  const toggle = document.createElement("button");
  toggle.className = "evidence-toggle";
  toggle.type = "button";
  const requestedCount = getRequestedCount();
  const visibleHits = mockData.hits.slice(0, 3);
  const requestedHits = mockData.hits.slice(0, requestedCount);
  toggle.innerHTML = `<span>3 principais evidências</span><span>+</span>`;

  const evidence = document.createElement("div");
  evidence.className = "rail-evidence";
  evidence.hidden = true;

  visibleHits.forEach((hit) => {
    const item = document.createElement("article");
    item.className = "rail-hit";
    item.innerHTML = `
      <p class="rail-hit-meta"><strong></strong> · <span></span><b></b></p>
      <p class="rail-hit-text"></p>
    `;
    item.querySelector("strong").textContent = hit.author;
    item.querySelector(".rail-hit-meta span").textContent = `${hit.title}, pág. ${hit.page}`;
    item.querySelector(".rail-hit-meta b").textContent = `score ${hit.score.toFixed(3)}`;
    item.querySelector(".rail-hit-text").textContent = hit.text;
    evidence.append(item);
  });

  const drawer = document.createElement("div");
  drawer.className = "evidence-drawer";
  drawer.hidden = true;
  drawer.innerHTML = `
    <div class="drawer-header">
      <div>
        <p class="eyebrow">Evidências completas</p>
        <h3>${requestedHits.length} conexões solicitadas</h3>
      </div>
      <button class="drawer-close" type="button" aria-label="Fechar evidências">×</button>
    </div>
    <div class="drawer-list"></div>
  `;
  const drawerList = drawer.querySelector(".drawer-list");
  requestedHits.forEach((hit, index) => {
    const item = document.createElement("article");
    item.className = "drawer-hit";
    item.innerHTML = `
      <span class="drawer-index">${String(index + 1).padStart(2, "0")}</span>
      <div>
        <p class="drawer-hit-meta"><strong></strong> · <span></span><b></b></p>
        <p class="drawer-hit-text"></p>
      </div>
    `;
    item.querySelector("strong").textContent = hit.author;
    item.querySelector(".drawer-hit-meta span").textContent = `${hit.title}, pág. ${hit.page}`;
    item.querySelector(".drawer-hit-meta b").textContent = `score ${hit.score.toFixed(3)}`;
    item.querySelector(".drawer-hit-text").textContent = hit.text;
    drawerList.append(item);
  });

  toggle.addEventListener("click", () => {
    drawer.hidden = false;
  });
  drawer.querySelector(".drawer-close").addEventListener("click", () => {
    drawer.hidden = true;
  });
  elements.connectionView.append(toggle, evidence, drawer);
}

function getRequestedCount() {
  const value = Number.parseInt(elements.connections.value, 10);
  return Math.min(Math.max(Number.isNaN(value) ? 3 : value, 1), mockData.hits.length);
}

function renderResult() {
  const card = document.createElement("div");
  card.className = "rail-card";

  const summary = document.createElement("p");
  summary.className = "rail-card-summary";
  appendFormattedText(summary, mockData.card);
  card.append(summary);

  const badge = document.createElement("span");
  badge.className = relationClass();
  badge.textContent = "COMPLEMENTO";
  card.append(badge);

  const citationLabel = document.createElement("span");
  citationLabel.className = "citation-label";
  citationLabel.textContent = "Fontes citadas:";
  card.append(citationLabel);

  const citations = document.createElement("ul");
  citations.className = "rail-citations";
  mockData.hits.slice(0, Math.min(getRequestedCount(), 2)).forEach((hit) => {
    const item = document.createElement("li");
    item.textContent = `${hit.author}, ${hit.title}, pág. ${hit.page}`;
    citations.append(item);
  });
  card.append(citations);

  elements.connectionView.innerHTML = `
    <div class="selected-snippet">
      <p class="eyebrow">Trecho consultado</p>
      <blockquote></blockquote>
    </div>
  `;
  elements.connectionView.querySelector("blockquote").textContent = mockData.selectedText;
  elements.connectionView.append(card);
  renderEvidence();
}

function renderNoConnection() {
  elements.connectionView.innerHTML = `
    <div class="selected-snippet">
      <p class="eyebrow">Trecho consultado</p>
      <blockquote></blockquote>
    </div>
    <div class="rail-card no-connection-card">
      <p class="state-title">Nenhuma conexão relevante identificada.</p>
      <p class="state-copy">Os trechos mais próximos aparecem abaixo como evidência.</p>
    </div>
  `;
  elements.connectionView.querySelector("blockquote").textContent = mockData.selectedText;
  renderEvidence();
}

function showConnectionView() {
  elements.searchView.hidden = true;
  elements.connectionView.hidden = false;
}

function showSearchView() {
  elements.searchView.hidden = false;
  elements.connectionView.hidden = true;
}

function runSearch() {
  showConnectionView();
  elements.searchButton.disabled = true;
  renderLoading();
  window.setTimeout(() => {
    elements.searchButton.disabled = false;
    renderResult();
  }, 900);
}

function placeSelectionAction() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !elements.bookText.contains(selection.anchorNode)) {
    elements.selectionAction.hidden = true;
    return;
  }

  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  const pageRect = elements.bookText.closest(".book-page").getBoundingClientRect();
  elements.selectionAction.style.left = `${rect.left - pageRect.left + rect.width / 2}px`;
  elements.selectionAction.style.top = `${rect.bottom - pageRect.top + 8}px`;
  elements.selectionAction.hidden = false;
}

elements.bookText.addEventListener("mouseup", placeSelectionAction);
elements.bookText.addEventListener("keyup", placeSelectionAction);
elements.connectSelection.addEventListener("click", () => {
  showConnectionView();
  runSearch();
});
elements.searchButton.addEventListener("click", runSearch);

renderInvite();
