// Troque este valor para revisar um estado sem executar o fluxo.
const DEMO_STATE = "empty";

const readingMock = {
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
  ],
};

const elements = {
  bookText: document.querySelector("#book-text"),
  selectionAction: document.querySelector("#selection-action"),
  connectSelection: document.querySelector("#connect-selection"),
  panel: document.querySelector("#connections-panel"),
  content: document.querySelector("#connection-content"),
  closePanel: document.querySelector("#close-panel"),
  openPanel: document.querySelector("#open-panel"),
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

function relationFromCard(card) {
  const relation = card.match(/\*\*(COMPLEMENTO|CONTRADIÇÃO|NUANCE|MESMO CONCEITO)\*\*/);
  return relation ? relation[1] : "COMPLEMENTO";
}

function relationClass(relation) {
  return {
    CONTRADIÇÃO: "contradiction",
    NUANCE: "nuance",
    "MESMO CONCEITO": "same-concept",
  }[relation] || "";
}

function renderInvite() {
  elements.content.innerHTML = `
    <div class="panel-invite">
      <p>Selecione um trecho para ver o que outros autores dizem.</p>
    </div>
  `;
}

function renderSelected() {
  elements.content.innerHTML = `
    <div class="selection-preview">
      <p class="eyebrow">Trecho selecionado</p>
      <blockquote class="selected-quote"></blockquote>
    </div>
    <button class="primary-button panel-search-button" type="button">
      Ver conexões
    </button>
  `;
  elements.content.querySelector(".selected-quote").textContent = readingMock.selectedText;
  elements.content.querySelector(".panel-search-button").addEventListener("click", runSearch);
}

function renderLoading() {
  elements.content.innerHTML = `
    <div class="selection-preview">
      <p class="eyebrow">Trecho selecionado</p>
      <blockquote class="selected-quote"></blockquote>
    </div>
    <div class="panel-skeleton" aria-live="polite" aria-label="Procurando conexões">
      <p class="state-title">Procurando conexões...</p>
      <span class="skeleton-line"></span>
      <span class="skeleton-line"></span>
      <span class="skeleton-line short"></span>
    </div>
  `;
  elements.content.querySelector(".selected-quote").textContent = readingMock.selectedText;
}

function renderError() {
  elements.content.innerHTML = `
    <div class="selection-preview">
      <p class="eyebrow">Trecho selecionado</p>
      <blockquote class="selected-quote"></blockquote>
    </div>
    <div class="panel-error">
      <p>Não foi possível buscar agora. Tente novamente.</p>
      <button class="retry-button" type="button">Tentar novamente</button>
    </div>
  `;
  elements.content.querySelector(".selected-quote").textContent = readingMock.selectedText;
  elements.content.querySelector(".retry-button").addEventListener("click", runSearch);
}

function renderNoConnection() {
  elements.content.innerHTML = `
    <div class="selection-preview">
      <p class="eyebrow">Trecho selecionado</p>
      <blockquote class="selected-quote"></blockquote>
    </div>
    <div class="connection-card">
      <p class="state-title">Nenhuma conexão relevante identificada.</p>
      <p class="state-copy">Os trechos mais próximos aparecem abaixo como evidência.</p>
    </div>
  `;
  elements.content.querySelector(".selected-quote").textContent = readingMock.selectedText;
  renderEvidence();
}

function renderResult() {
  const relation = relationFromCard(readingMock.card);
  const card = document.createElement("div");
  card.className = "connection-card";

  const summary = document.createElement("p");
  summary.className = "card-summary";
  appendFormattedText(summary, readingMock.card);
  card.append(summary);

  const badge = document.createElement("span");
  badge.className = `relation-badge ${relationClass(relation)}`;
  badge.textContent = relation;
  card.append(badge);

  const citationLabel = document.createElement("span");
  citationLabel.className = "citation-label";
  citationLabel.textContent = "Fontes citadas:";
  card.append(citationLabel);

  const citations = document.createElement("ul");
  citations.className = "panel-citations";
  readingMock.hits.slice(0, 2).forEach((hit) => {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.className = "source-link";
    link.href = "#";
    link.textContent = `${hit.author}, ${hit.title}, pág. ${hit.page}`;
    link.addEventListener("click", (event) => event.preventDefault());
    item.append(link);
    citations.append(item);
  });
  card.append(citations);

  elements.content.innerHTML = `
    <div class="selection-preview">
      <p class="eyebrow">Trecho selecionado</p>
      <blockquote class="selected-quote"></blockquote>
    </div>
  `;
  elements.content.querySelector(".selected-quote").textContent = readingMock.selectedText;
  elements.content.append(card);
  renderEvidence();
}

function renderEvidence() {
  const toggle = document.createElement("button");
  toggle.className = "evidence-toggle";
  toggle.type = "button";
  toggle.innerHTML = "<span>Trechos recuperados</span><span>+</span>";

  const evidence = document.createElement("div");
  evidence.className = "panel-evidence";
  evidence.hidden = true;
  readingMock.hits.forEach((hit) => {
    const item = document.createElement("article");
    item.className = "panel-hit";
    item.innerHTML = `
      <p class="panel-hit-meta"><strong></strong> · <span></span><span class="panel-hit-score"></span></p>
      <p class="panel-hit-text"></p>
    `;
    item.querySelector("strong").textContent = hit.author;
    item.querySelector(".panel-hit-meta span").textContent = `${hit.title}, pág. ${hit.page}`;
    item.querySelector(".panel-hit-score").textContent = `score ${hit.score.toFixed(3)}`;
    item.querySelector(".panel-hit-text").textContent = hit.text;
    evidence.append(item);
  });

  toggle.addEventListener("click", () => {
    evidence.hidden = !evidence.hidden;
    toggle.lastElementChild.textContent = evidence.hidden ? "+" : "−";
  });
  elements.content.append(toggle, evidence);
}

function renderState(state) {
  if (state === "empty") {
    renderInvite();
  } else if (state === "selection") {
    renderSelected();
  } else if (state === "loading") {
    renderLoading();
  } else if (state === "error") {
    renderError();
  } else if (state === "no-connection") {
    renderNoConnection();
  } else {
    renderResult();
  }
}

function runSearch() {
  renderLoading();
  window.setTimeout(() => renderState("result"), 900);
}

function showSelectionAction() {
  const selection = window.getSelection();
  if (!selection || selection.isCollapsed || !elements.bookText.contains(selection.anchorNode)) {
    elements.selectionAction.hidden = true;
    return;
  }

  const range = selection.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  const parentRect = elements.bookText.closest(".book-page").getBoundingClientRect();
  elements.selectionAction.style.left = `${rect.left - parentRect.left + rect.width / 2}px`;
  elements.selectionAction.style.top = `${rect.bottom - parentRect.top}px`;
  elements.selectionAction.hidden = false;
  elements.panel.classList.add("is-open");
  elements.openPanel.hidden = true;
  renderState("selection");
}

elements.bookText.addEventListener("mouseup", showSelectionAction);
elements.bookText.addEventListener("keyup", showSelectionAction);
elements.connectSelection.addEventListener("click", runSearch);
elements.closePanel.addEventListener("click", () => {
  elements.panel.classList.remove("is-open");
  elements.openPanel.hidden = false;
});
elements.openPanel.addEventListener("click", () => {
  elements.panel.classList.add("is-open");
  elements.openPanel.hidden = true;
});

renderState(DEMO_STATE);
