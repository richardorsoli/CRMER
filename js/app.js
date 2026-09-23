/*
 * CRMER — carteira comercial da EHE Indústria.
 * Scripts clássicos, nesta ordem: mock-data.js, auth.js, app.js.
 * Assim o protótipo continua abrindo direto no navegador.
 */
(() => {
  "use strict";

  const mock = window.CRMER_MOCK;
  const auth = window.CRMER_AUTH;
  if (!mock || !auth) {
    throw new Error("CRMER: carregue js/mock-data.js e js/auth.js antes de js/app.js.");
  }

  const TODAY = mock.TODAY;

  const RANKINGS = mock.RANKINGS;
  const LINHAS = mock.LINHAS;
  const UFS = mock.UFS;
  const EHE = mock.EHE;

  function cloneClient(client) {
    return {
      ...client,
      linhas: [...(client.linhas || [])],
      pedidos: (client.pedidos || []).map((order) => ({
        ...order,
        ...(order.nfe_info ? { nfe_info: { ...order.nfe_info } } : {})
      })),
      orcamentos: (client.orcamentos || []).map((quote) => ({ ...quote })),
      processos: (client.processos || []).map((proc) => ({ ...proc }))
    };
  }

  const state = {
    view: "dashboard",
    ranking: "contato",
    session: null,
    drawerId: null,
    lastFocus: null,
    clients: mock.clients.map(cloneClient),
    products: mock.produtos || [],
    carteiraFonte: "simulada",
    produtosFonte: "simulada",
    productLine: "todos",
    productQuery: "",
    historicoPrecos: [],
    biPeriodo: "12m",
    biCache: null,
    searchIndex: -1,
    searchTimer: 0,
    atividades: [],
    atividadesFiltro: "todos",
    atividadeClienteId: null,
    funil: [],
    perdas: [],
    funilPronto: false
  };

  const FUNIL_ETAPAS = ["orcamentos", "negociacoes", "producao"];
  const PERDA_MOTIVOS = {
    "PREÇO": ["Preço acima do concorrente", "Sem verba"],
    "PRAZO": ["Prazo de entrega longo"],
    "FATURAMENTO": ["Prazo baixo de pagamento", "Não parcelamento"],
    "PROJETO NÃO ATENDE": ["Especificação fora de escopo"]
  };

  const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  let toastTimer = 0;
  let drawerKeyBound = false;

  function money(value) {
    return brl.format(value);
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function formatDate(iso) {
    if (!iso) return "Não informado";
    const parts = iso.split("-");
    if (parts.length !== 3) return iso;
    return `${parts[2]}/${parts[1]}/${parts[0]}`;
  }

  function daysSince(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return 0;
    const [year, month, day] = iso.split("-").map(Number);
    const [ty, tm, td] = TODAY.split("-").map(Number);
    const diff = Date.UTC(ty, tm - 1, td) - Date.UTC(year, month - 1, day);
    return Math.round(diff / 86400000);
  }

  function snippet(text, max) {
    const clean = String(text || "").replace(/\s+/g, " ").trim();
    if (clean.length <= max) return clean;
    return `${clean.slice(0, max - 1)}…`;
  }

  function telHref(phone) {
    const digits = String(phone).replace(/\D/g, "");
    return digits ? `tel:+55${digits}` : "";
  }

  function getClient(id) {
    return state.clients.find((client) => client.id === id);
  }

  function countRanking(ranking) {
    return state.clients.filter((client) => client.ranking === ranking).length;
  }

  function isDue(client) {
    return !client.proximoContato || client.proximoContato <= TODAY;
  }

  function dueContacts() {
    return state.clients
      .filter((client) => client.ranking === "contato" && isDue(client))
      .slice()
      .sort((a, b) => (a.proximoContato || "").localeCompare(b.proximoContato || ""));
  }

  function openQuotes() {
    const rows = [];
    state.clients.forEach((client) => {
      client.orcamentos.forEach((quote) => rows.push({ client, quote }));
    });
    rows.sort((a, b) => a.quote.data.localeCompare(b.quote.data));
    return rows;
  }

  function statusOf(client) {
    if (client.ranking === "contato") {
      if (!client.proximoContato) {
        return { className: "badge-atrasado", label: "Sem data de contato" };
      }
      const delta = daysSince(client.proximoContato);
      if (delta > 0) {
        return { className: "badge-atrasado", label: `Atrasado · ${delta} dia${delta > 1 ? "s" : ""}` };
      }
      if (delta === 0) return { className: "badge-contato", label: "Contato hoje" };
      return { className: "badge-contato", label: `Agendado · ${formatDate(client.proximoContato)}` };
    }
    if (client.ranking === "resposta") {
      const quote = client.orcamentos.slice().sort((a, b) => a.data.localeCompare(b.data))[0];
      if (!quote) return { className: "badge-resposta", label: "Aguardando retorno" };
      const delta = daysSince(quote.data);
      return { className: "badge-resposta", label: `Sem retorno · ${delta} dia${delta === 1 ? "" : "s"}` };
    }
    if (client.ranking === "sazonal") {
      return { className: "badge-sazonal", label: client.janelaSazonal || "Janela sazonal" };
    }
    if (!client.ultimaCompra) return { className: "badge-inativo", label: "Inativo · sem compra" };
    const delta = daysSince(client.ultimaCompra);
    return { className: "badge-inativo", label: `Inativo · ${delta} dias` };
  }

  function extraBadges(client) {
    const badges = [];
    if (client.prioridade === "alta") badges.push('<span class="badge badge-alta">Prioridade alta</span>');
    if (client.curva) badges.push(`<span class="badge badge-curva">Curva ${escapeHtml(client.curva)}</span>`);
    return badges.join("");
  }

  function chips(linhas) {
    return linhas.map((linha) => `<span class="chip" data-line="${escapeHtml(linha)}">${escapeHtml(linha)}</span>`).join("");
  }

  function kpiCard(title, value, hint, extra) {
    return `<article class="kpi"><h3>${title}</h3><p class="kpi-value">${value}</p><p class="kpi-hint">${hint}</p>${extra || ""}</article>`;
  }

  function renderKpis() {
    const due = dueContacts();
    const overdue = due.filter((client) => client.proximoContato && client.proximoContato < TODAY).length;
    const quotes = openQuotes();
    const quoteTotal = quotes.reduce((sum, row) => sum + row.quote.valor, 0);
    const progress = Math.max(0, Math.min(100, (EHE.faturamentoNatalia / EHE.metaMes) * 100));
    const remaining = Math.max(0, EHE.metaMes - EHE.faturamentoNatalia);
    const pctLabel = (EHE.faturamentoNatalia / EHE.metaMes).toLocaleString("pt-BR", {
      style: "percent",
      maximumFractionDigits: 1
    });
    const bar = `<div class="progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${Math.round(progress)}" aria-label="Progresso da meta de setembro"><span style="width:${progress.toFixed(1)}%"></span></div>`;

    document.getElementById("kpi-grid").innerHTML = [
      kpiCard("Faturamento do mês", money(EHE.faturamentoNatalia), `Setembro 2026 · ${pctLabel} da meta`, bar),
      kpiCard("Meta do mês", money(EHE.metaMes), `Faltam ${money(remaining)}`),
      kpiCard("Orçamentos abertos", String(quotes.length), money(quoteTotal)),
      kpiCard("Follow-ups de hoje", String(due.length), overdue ? `${overdue} atrasado${overdue > 1 ? "s" : ""}` : "Nenhum atrasado")
    ].join("");
  }

  function garantirFunil() {
    if (state.funilPronto) return;
    const etapas = ["orcamentos", "negociacoes", "producao"];
    state.funil = openQuotes().map(({ client, quote }, index) => ({
      id: String(quote.codigo || `${client.id}-${index}`),
      clienteId: client.id,
      cliente: client.razaoSocial,
      valor: Number(quote.valor) || 0,
      data: quote.data || TODAY,
      etapa: etapas[index % etapas.length]
    }));
    state.funilPronto = true;
  }

  function moverEtapa(id, destino) {
    const card = state.funil.find((item) => item.id === id);
    if (!card || !FUNIL_ETAPAS.includes(destino)) return;
    card.etapa = destino;
    renderFunil();
  }

  function deslocarEtapa(id, sentido) {
    const card = state.funil.find((item) => item.id === id);
    if (!card) return;
    const indice = FUNIL_ETAPAS.indexOf(card.etapa);
    const proximo = FUNIL_ETAPAS[indice + sentido];
    if (!proximo) return;
    card.etapa = proximo;
    renderFunil();
  }

  function cardFunilHtml(card) {
    return `<article class="kanban-card" draggable="true" data-processo-id="${escapeHtml(card.id)}"><p class="kanban-cliente">${escapeHtml(card.cliente)}</p><p class="kanban-valor">${money(card.valor)}</p><p class="kanban-data">${escapeHtml(formatDate(card.data))}</p><div class="kanban-actions"><button type="button" class="btn btn-small" data-action="avancar-etapa" data-id="${escapeHtml(card.id)}">Avançar Etapa</button><button type="button" class="btn btn-small" data-action="voltar-etapa" data-id="${escapeHtml(card.id)}">Voltar Etapa</button><button type="button" class="btn btn-small" data-action="marcar-perdido" data-id="${escapeHtml(card.id)}">Marcar como Perdido</button></div></article>`;
  }

  function renderFunil() {
    garantirFunil();
    FUNIL_ETAPAS.forEach((etapa) => {
      const cards = state.funil.filter((item) => item.etapa === etapa);
      const total = cards.reduce((soma, item) => soma + item.valor, 0);
      const lista = document.querySelector(`[data-funil-lista="${etapa}"]`);
      const meta = document.querySelector(`[data-funil-meta="${etapa}"]`);
      if (lista) {
        lista.innerHTML = cards.length
          ? cards.map(cardFunilHtml).join("")
          : '<p class="empty-inline">Nenhum processo nesta etapa.</p>';
      }
      if (meta) meta.textContent = `${cards.length} · ${money(total)}`;
    });
    renderPerdas();
  }

  function renderPerdas() {
    Object.keys(PERDA_MOTIVOS).forEach((categoria) => {
      const alvo = document.querySelector(`[data-perda-count="${categoria}"]`);
      if (!alvo) return;
      const qtd = state.perdas.filter((item) => item.categoria === categoria).length;
      alvo.textContent = String(qtd);
    });
  }

  function preencherMotivosPerda(categoria) {
    const motivo = document.getElementById("perda-motivo");
    if (!motivo) return;
    const opcoes = PERDA_MOTIVOS[categoria] || [];
    motivo.innerHTML = opcoes.length
      ? opcoes.map((item) => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join("")
      : '<option value="">Selecione a categoria</option>';
  }

  const MODAIS = ["modal-feedback", "modal-changelog", "modal-perda", "modal-cliente"];

  function fecharTodosModais(exceto) {
    MODAIS.forEach((id) => {
      if (id === exceto) return;
      fecharModal(document.getElementById(id));
    });
  }

  function abrirModal(dialog) {
    if (!dialog) return;
    fecharTodosModais(dialog.id);
    dialog.hidden = false;
    dialog.classList.add("ativo");
    if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
  }

  function fecharModal(dialog) {
    if (!dialog) return;
    dialog.classList.remove("ativo", "open");
    if (dialog.open) dialog.close();
    dialog.hidden = true;
  }

  function abrirPerda(id) {
    const form = document.getElementById("form-perda");
    const dialog = document.getElementById("modal-perda");
    if (!form || !dialog || !state.funil.some((item) => item.id === id)) return;
    form.reset();
    document.getElementById("perda-processo-id").value = id;
    preencherMotivosPerda("");
    abrirModal(dialog);
  }

  function fecharPerda() {
    fecharModal(document.getElementById("modal-perda"));
  }

  function confirmarPerda(form) {
    const id = form.processoId.value;
    const categoria = form.categoria.value;
    const motivo = form.motivo.value;
    const card = state.funil.find((item) => item.id === id);
    if (!card || !PERDA_MOTIVOS[categoria] || !motivo) return;
    state.funil = state.funil.filter((item) => item.id !== id);
    state.perdas.push({
      id: card.id,
      cliente: card.cliente,
      valor: card.valor,
      categoria,
      motivo,
      observacao: form.observacao.value.trim()
    });
    fecharPerda();
    renderFunil();
  }

  function renderTeam() {
    const totalPecas = EHE.linhas.reduce((sum, line) => sum + line.pecas, 0);
    const share = (EHE.faturamentoNatalia / EHE.faturamentoEquipe).toLocaleString("pt-BR", {
      style: "percent",
      maximumFractionDigits: 1
    });
    document.getElementById("team-revenue").textContent = money(EHE.faturamentoEquipe);
    document.getElementById("team-caption").textContent = `Setembro 2026 · a Natália responde por ${share} deste faturamento (${money(EHE.faturamentoNatalia)}).`;
    document.getElementById("line-chart").innerHTML = EHE.linhas.map((line) => {
      const volumeShare = (line.pecas / totalPecas) * 100;
      const volumeLabel = volumeShare.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
      return `<div class="line-row"><div class="line-row-head"><span class="chip" data-line="${escapeHtml(line.nome)}">${escapeHtml(line.nome)}</span><strong>${line.pecas.toLocaleString("pt-BR")} peças</strong></div><div class="bar" aria-hidden="true"><span data-line="${escapeHtml(line.nome)}" style="width:${volumeShare.toFixed(1)}%"></span></div><p class="line-meta">${volumeLabel}% do volume · ${money(line.faturamento)}</p></div>`;
    }).join("");
  }

  function renderDashboard() {
    renderKpis();
    renderFunil();
    renderTeam();
    renderFonte();
  }

  function renderFonte() {
    const note = document.getElementById("carteira-fonte");
    if (!note) return;
    note.textContent = state.carteiraFonte === "arquivo"
      ? "Carteira lida do arquivo local da consulta Nomus (fase 1). Não é integração ao vivo. Anotações e clientes incluídos aqui permanecem neste navegador."
      : "Carteira simulada: o arquivo da consulta Nomus não abriu nesta sessão. Anotações e clientes incluídos aqui permanecem neste navegador.";
  }

  function cardTemplate(client) {
    const status = statusOf(client);
    const processos = blocoProcessos(client, true);
    return `<article class="client-card" data-ranking="${escapeHtml(client.ranking)}"><div class="client-card-top"><div><h3>${escapeHtml(client.razaoSocial)}</h3><p class="client-meta">${escapeHtml(client.tipo)} · ${escapeHtml(client.cidade)}/${escapeHtml(client.uf)}</p></div><div class="badge-row"><span class="badge ${status.className}">${escapeHtml(status.label)}</span>${extraBadges(client)}</div></div><p class="client-contact">${escapeHtml(client.contato)} · ${escapeHtml(client.cargo)}</p><div class="chips">${chips(client.linhas)}</div><p class="client-summary">${escapeHtml(client.resumo)}</p>${processos}<div class="client-card-foot"><span>12 meses <strong class="money">${money(client.faturamento12m)}</strong></span><button type="button" class="btn btn-small" data-action="open-client" data-id="${escapeHtml(client.id)}">Abrir ficha</button></div></article>`;
  }

  function renderClientList() {
    document.querySelectorAll("[data-count]").forEach((element) => {
      element.textContent = String(countRanking(element.dataset.count));
    });
    document.querySelectorAll("[data-action='show-ranking']").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.ranking === state.ranking));
    });

    const ranking = RANKINGS[state.ranking];
    const help = document.getElementById("ranking-help");
    const dueCount = dueContacts().length;
    const laterCount = countRanking("contato") - dueCount;
    help.textContent = state.ranking === "contato" && laterCount > 0
      ? `${ranking.help} ${dueCount} para hoje ou atrasados · ${laterCount} reagendado${laterCount > 1 ? "s" : ""}.`
      : ranking.help;

    document.getElementById("portfolio-count").textContent = `${state.clients.length} clientes na carteira · ${countRanking(state.ranking)} nesta fila`;
    document.getElementById("client-list").setAttribute("aria-labelledby", `tab-rank-${state.ranking}`);

    const list = state.clients.filter((client) => client.ranking === state.ranking).slice();
    const root = document.getElementById("client-list");
    if (!list.length) {
      root.innerHTML = '<p class="empty">Nenhum cliente nesta fila.</p>';
      return;
    }

    if (state.ranking === "contato") {
      const due = list.filter(isDue).sort((a, b) => (a.proximoContato || "").localeCompare(b.proximoContato || ""));
      const later = list.filter((client) => !isDue(client)).sort((a, b) => a.proximoContato.localeCompare(b.proximoContato));
      const parts = [];
      if (due.length) {
        if (later.length) parts.push('<h3 class="group-label">Para hoje e atrasados</h3>');
        parts.push(due.map(cardTemplate).join(""));
      }
      if (later.length) {
        if (due.length) parts.push('<h3 class="group-label">Reagendados</h3>');
        parts.push(later.map(cardTemplate).join(""));
      }
      root.innerHTML = parts.join("");
      return;
    }

    if (state.ranking === "resposta") {
      list.sort((a, b) => {
        const aDate = a.orcamentos.reduce((oldest, quote) => (quote.data < oldest ? quote.data : oldest), "9999-99-99");
        const bDate = b.orcamentos.reduce((oldest, quote) => (quote.data < oldest ? quote.data : oldest), "9999-99-99");
        return aDate.localeCompare(bDate);
      });
    } else if (state.ranking === "inativos") {
      list.sort((a, b) => b.faturamento12m - a.faturamento12m);
    } else {
      list.sort((a, b) => a.razaoSocial.localeCompare(b.razaoSocial, "pt-BR"));
    }
    root.innerHTML = list.map(cardTemplate).join("");
  }

  function detail(label, value, wide) {
    return `<div class="${wide ? "detail-wide" : ""}"><dt>${label}</dt><dd>${value}</dd></div>`;
  }

  function contactLink(client) {
    if (!client.email) return "Não informado";
    return `<a href="mailto:${escapeHtml(client.email)}">${escapeHtml(client.email)}</a>`;
  }

  function phoneLink(client) {
    if (!client.telefone) return "Não informado";
    return `<a href="${escapeHtml(telHref(client.telefone))}">${escapeHtml(client.telefone)}</a>`;
  }

  function esperaOrcamento(iso) {
    const delta = daysSince(iso);
    if (delta < 0) {
      const falta = -delta;
      return `retorno em ${falta} dia${falta === 1 ? "" : "s"}`;
    }
    if (delta === 0) return "enviado hoje";
    return `há ${delta} dia${delta === 1 ? "" : "s"}`;
  }

  function ehProposta(etapa) {
    const texto = fold(etapa);
    return texto.includes("proposta") && texto.includes("orcamento");
  }

  function formatarProgramacao(valor) {
    const texto = String(valor || "").trim();
    if (!texto) return "sem data programada";
    const nomus = texto.match(/^(\d{2}\/\d{2}\/\d{4})(?:\s+(\d{2}:\d{2})(?::\d{2})?)?$/);
    if (nomus) return nomus[2] ? `${nomus[1]} ${nomus[2]}` : nomus[1];
    const iso = texto.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2}))?/);
    if (iso) {
      const data = `${iso[3]}/${iso[2]}/${iso[1]}`;
      return iso[4] ? `${data} ${iso[4]}:${iso[5]}` : data;
    }
    return texto;
  }

  function blocoProcessos(client, somenteProposta) {
    const lista = (client.processos || []).filter((proc) => {
      if (!proc || typeof proc !== "object") return false;
      if (somenteProposta) return ehProposta(proc.etapa);
      return ehProposta(proc.etapa) || String(proc.dataHoraProgramada || "").trim();
    });
    if (!lista.length) return "";
    const cards = lista.map((proc) => {
      const proposta = ehProposta(proc.etapa);
      const kicker = proposta ? "Proposta / Orçamentos" : escapeHtml(proc.etapa || "Tarefa de vendas");
      const prioridade = proc.prioridade ? escapeHtml(proc.prioridade) : "não informada";
      const quando = escapeHtml(formatarProgramacao(proc.dataHoraProgramada));
      const detalhe = proc.descricao ? `<p>${escapeHtml(proc.descricao)}</p>` : "";
      return `<article class="process-card"><p class="process-kicker">${kicker}</p>${detalhe}<p><strong>Prioridade:</strong> ${prioridade}</p><p>Retorno programado: ${quando}</p></article>`;
    }).join("");
    if (somenteProposta) return `<div class="process-list">${cards}</div>`;
    return `<section class="process-list"><h3>Tarefas programadas</h3>${cards}</section>`;
  }

  function blocoNfe(order) {
    const info = order && order.nfe_info;
    if (!info || typeof info !== "object") return "";
    const numero = String(info.numero_nf || "").trim();
    const transportadora = String(info.transportadora || "").trim();
    const destino = String(info.destino_obra || "").trim();
    if (!numero && !transportadora && !destino) return "";
    const rotulo = numero ? `NF nº ${numero}` : "NF-e";
    const faixa = transportadora ? `${rotulo} | ${transportadora}` : rotulo;
    const entrega = destino ? `<span class="nfe-destino">📍 Destino/Obra: ${escapeHtml(destino)}</span>` : "";
    return `<span class="nfe-linha"><span class="badge badge-nfe">${escapeHtml(faixa)}</span>${entrega}</span>`;
  }

  function clientDrawerHtml(client) {
    const quotes = client.orcamentos.slice().sort((a, b) => a.data.localeCompare(b.data));
    const quoteBlock = quotes.length
      ? `<section><h3>${quotes.length > 1 ? "Orçamentos enviados sem retorno" : "Orçamento enviado sem retorno"}</h3><ul class="quote-block">${quotes.map((quote) => {
        const wait = esperaOrcamento(quote.data);
        return `<li class="quote-line"><span><strong>${escapeHtml(quote.item)}</strong><span class="meta">${escapeHtml(quote.codigo)} · ${formatDate(quote.data)} ·${wait}</span></span><strong class="money">${money(quote.valor)}</strong></li>`;
      }).join("")}</ul></section>`
      : "";

    const orders = client.pedidos.length
      ? `<ul class="orders">${client.pedidos.map((order) => {
        const condicao = order.condicaoPagamento ? `<span class="meta">Condição: ${escapeHtml(order.condicaoPagamento)}</span>` : "";
        return `<li class="order-row"><span><strong>${escapeHtml(order.item)}</strong><span class="meta">${escapeHtml(order.codigo)} · ${formatDate(order.data)} ·${order.quantidade} un. · Nomus</span>${condicao}${blocoNfe(order)}</span><strong class="money">${money(order.valor)}</strong></li>`;
      }).join("")}</ul>`
      : '<p class="empty">Nenhum pedido recente retornado pelo Nomus para esta ficha.</p>';

    return `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <p class="drawer-lead" style="margin:0;">${escapeHtml(client.resumo)}</p>
        <button type="button" class="btn btn-secondary" style="font-size:12px; padding:4px 8px;" data-action="editar-cliente">Editar cliente</button>
      </div>

      <!-- MODO LEITURA -->
      <dl class="details" id="drawer-view-mode">
        ${detail("Nome fantasia", escapeHtml(client.nomeFantasia || "Não informado"))}
        ${detail("CNPJ", escapeHtml(client.cnpj || "Não informado"))}
        ${detail("Tipo", escapeHtml(client.tipo))}
        ${detail("Cidade", `${escapeHtml(client.cidade)}/${escapeHtml(client.uf)}`)}
        ${detail("Contato", escapeHtml(client.contato))}
        ${detail("Cargo", escapeHtml(client.cargo))}
        ${detail("E-mail", contactLink(client))}
        ${detail("Telefone", phoneLink(client))}
        ${detail("WhatsApp", client.whatsapp ? phoneLink({ telefone: client.whatsapp }) : "Não informado")}
        ${detail("Faturamento em 12 meses", money(client.faturamento12m))}
        ${detail("Última compra", client.ultimaCompra ? formatDate(client.ultimaCompra) : "Sem compra registrada")}
        ${detail("Linhas", `<div class="chips">${chips(client.linhas)}</div>`, true)}
      </dl>

      ${blocoProcessos(client, false)}
      ${quoteBlock}
      <section>
        <h3>Histórico recente de pedidos</h3>
        <p class="source-note">Simulação de consulta ao Nomus Industrial (fase 1). Somente leitura.</p>
        ${orders}
      </section>
      ${blocoPrecos(client)}
      <form id="form-notes" class="notes-form">
        <h3>Anotações da Natália</h3>
        <label>
          Observações da obra
          <textarea name="anotacoes" rows="5">${escapeHtml(client.anotacoes)}</textarea>
        </label>
        <label>
          Próximo contato
          <input type="date" name="proximoContato" value="${escapeHtml(client.proximoContato || "")}">
          <span class="field-hint">Uma data futura tira o cliente da agenda de hoje e o deixa em Reagendados, na mesma fila.</span>
        </label>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Salvar anotação</button>
        </div>
      </form>`;
  }

  function createFormHtml() {
    const rankingOptions = Object.entries(RANKINGS).map(([id, ranking]) => {
      const selected = id === state.ranking ? " selected" : "";
      return `<option value="${id}"${selected}>${escapeHtml(ranking.label)}</option>`;
    }).join("");
    const lineOptions = LINHAS.map((linha) => `<option value="${escapeHtml(linha)}">${escapeHtml(linha)}</option>`).join("");
    const ufOptions = UFS.map((uf) => `<option value="${uf}"${uf === "SP" ? " selected" : ""}>${uf}</option>`).join("");
    return `
      <form id="form-create" class="create-form">
        <p class="source-note">A ficha nasce na carteira da Natália. O histórico de pedidos só aparece quando a fase 1 do Nomus estiver ligada.</p>
        <p class="form-feedback" role="alert" hidden></p>
        <label>Razão social<input type="text" name="razaoSocial" autocomplete="organization"></label>
        <label>Contato<input type="text" name="contato" autocomplete="name"></label>
        <label>Cidade<input type="text" name="cidade"></label>
        <label>UF<select name="uf">${ufOptions}</select></label>
        <label>Tipo<select name="tipo"><option>Construtora</option><option>Instaladora</option></select></label>
        <label>Linha principal<select name="linha">${lineOptions}</select></label>
        <label>Fila<select name="ranking">${rankingOptions}</select></label>
        <label>Observações da obra<textarea name="anotacoes" rows="4"></textarea></label>
        <label>Próximo contato<input type="date" name="proximoContato" value="${state.ranking === "contato" ? TODAY : ""}"></label>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary">Incluir na carteira</button>
        </div>
      </form>`;
  }

  function showDrawer() {
    const root = document.getElementById("drawer-root");
    if (root.hidden) {
      state.lastFocus = document.activeElement;
      if (!drawerKeyBound) {
        document.addEventListener("keydown", onDrawerKey);
        drawerKeyBound = true;
      }
    }
    root.hidden = false;
    document.body.classList.add("drawer-open");
    document.getElementById("drawer-title").focus();
  }

  function closeDrawer() {
    const root = document.getElementById("drawer-root");
    if (root.hidden) return;
    root.hidden = true;
    document.body.classList.remove("drawer-open");
    if (drawerKeyBound) {
      document.removeEventListener("keydown", onDrawerKey);
      drawerKeyBound = false;
    }
    if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
    state.drawerId = null;
  }

  function onDrawerKey(event) {
    if (event.key !== "Escape" || event.defaultPrevented) return;
    closeDrawer();
  }

  function openClient(id) {
    const client = getClient(id);
    if (!client) return;
    clearSearch();
    state.drawerId = id;
    document.getElementById("drawer-kicker").textContent = RANKINGS[client.ranking].label;
    document.getElementById("drawer-title").textContent = client.razaoSocial;
    document.getElementById("drawer-body").innerHTML = clientDrawerHtml(client);
    ligarPrecos(client);
    showDrawer();
  }

  function openCreate() {
    abrirModalCliente();
  }

  function abrirModalCliente(id) {
    const dialog = document.getElementById("modal-cliente");
    const form = document.getElementById("form-cliente");
    const titulo = document.getElementById("modal-cliente-titulo");
    const erro = document.getElementById("modal-cliente-erro");
    if (!dialog || !form) return;
    form.reset();
    if (erro) {
      erro.hidden = true;
      erro.textContent = "";
    }
    const client = id ? getClient(id) : null;
    form.dataset.modo = client ? "editar" : "criar";
    form.dataset.id = client ? client.id : "";
    titulo.textContent = client ? "Editar cliente" : "Novo cliente";
    if (client) {
      form.tipoPessoa.value = String(client.tipoPessoa || 1);
      form.cnpj.value = client.cnpj || "";
      form.razaoSocial.value = client.razaoSocial || "";
      form.nomeFantasia.value = client.nomeFantasia || "";
      form.email.value = client.email || "";
      form.telefone.value = client.telefone || client.whatsapp || "";
      form.logradouro.value = client.logradouro || "";
      form.bairro.value = client.bairro || "";
      form.cep.value = client.cep || "";
      form.cidade.value = client.cidade || "";
      if ([...form.uf.options].some((option) => option.value === client.uf)) form.uf.value = client.uf;
      form.observacoes.value = client.anotacoes || "";
    }
    abrirModal(dialog);
  }

  function fecharModalCliente() {
    fecharModal(document.getElementById("modal-cliente"));
  }

  async function salvarModalCliente(form) {
    const erro = document.getElementById("modal-cliente-erro");
    const botao = form.querySelector("[type='submit']");
    const dados = {
      tipoPessoa: Number(form.tipoPessoa.value) || 1,
      cnpj: form.cnpj.value.trim(),
      razaoSocial: form.razaoSocial.value.trim(),
      nomeFantasia: form.nomeFantasia.value.trim(),
      email: form.email.value.trim(),
      telefone: form.telefone.value.trim(),
      logradouro: form.logradouro.value.trim(),
      bairro: form.bairro.value.trim(),
      cep: form.cep.value.trim(),
      cidade: form.cidade.value.trim(),
      uf: form.uf.value.trim(),
      observacoes: form.observacoes.value.trim()
    };
    const modo = form.dataset.modo === "editar" ? "editar" : "criar";
    let url = "/api/clientes";
    let method = "POST";
    if (modo === "editar") {
      const atual = getClient(form.dataset.id);
      if (!atual) return;
      const nomusId = atual.nomusId || String(atual.id).replace(/^nomus-/, "");
      url = `/api/clientes/${nomusId}`;
      method = "PUT";
    }
    if (erro) erro.hidden = true;
    if (botao) botao.disabled = true;
    try {
      const resposta = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json; charset=utf-8" },
        body: JSON.stringify(dados)
      });
      const resultado = await resposta.json();
      if (!resposta.ok || !resultado.sucesso) {
        throw new Error(resultado.erro || "Falha ao gravar no Nomus");
      }
      if (modo === "editar") {
        const client = getClient(form.dataset.id);
        Object.assign(client, {
          razaoSocial: dados.razaoSocial,
          nomeFantasia: dados.nomeFantasia,
          cnpj: dados.cnpj,
          tipoPessoa: dados.tipoPessoa,
          telefone: dados.telefone,
          email: dados.email,
          anotacoes: dados.observacoes,
          cidade: dados.cidade,
          uf: dados.uf,
          logradouro: dados.logradouro,
          bairro: dados.bairro,
          cep: dados.cep
        });
        renderClientList();
        renderDashboard();
        if (state.drawerId === client.id) openClient(client.id);
      } else if (resultado.cliente) {
        const novo = normalizarCliente({
          ...resultado.cliente,
          ranking: "contato",
          tipo: dados.tipoPessoa === 2 ? "Pessoa física" : "Pessoa jurídica",
          contato: dados.nomeFantasia || dados.razaoSocial,
          cargo: "Comprador",
          resumo: dados.observacoes || "Cliente incluído no Nomus.",
          linhas: [],
          faturamento12m: 0,
          whatsapp: dados.telefone,
          proximoContato: TODAY,
          origemManual: true
        });
        state.clients.unshift(novo);
        persistirCarteira();
        renderClientList();
        renderDashboard();
      }
      toast(modo === "editar" ? "Cliente atualizado no Nomus." : "Cliente criado no Nomus.");
      fecharModalCliente();
    } catch (err) {
      if (erro) {
        erro.hidden = false;
        erro.textContent = err.message;
      }
    } finally {
      if (botao) botao.disabled = false;
    }
  }

  function precosDoCliente(client) {
    if (Array.isArray(client.precos) && client.precos.length) {
      return client.precos.map((row) => ({
        nomeProduto: String(row.nomeProduto || row.item || "Item"),
        dataEmissao: String(row.dataEmissao || row.data || ""),
        valorUnitario: Number(row.valorUnitario),
        condicaoPagamento: String(row.condicaoPagamento || "")
      })).filter((row) => Number.isFinite(row.valorUnitario));
    }
    return (client.pedidos || []).map((order) => {
      const quantidade = Number(order.quantidade) || 0;
      const unitario = order.valorUnitario != null
        ? Number(order.valorUnitario)
        : (quantidade ? Number(order.valor) / quantidade : Number(order.valor));
      return {
        nomeProduto: String(order.item || "Item"),
        dataEmissao: String(order.data || ""),
        valorUnitario: unitario,
        condicaoPagamento: String(order.condicaoPagamento || "")
      };
    }).filter((row) => Number.isFinite(row.valorUnitario));
  }

  function blocoPrecos(client) {
    const precos = precosDoCliente(client);
    if (!precos.length) return "";
    const condicoes = [...new Set(precos.map((row) => row.condicaoPagamento).filter(Boolean))];
    const banner = condicoes.length
      ? `<p class="condition-banner"><strong>Condição negociada.</strong> ${condicoes.map((item) => escapeHtml(item)).join(" · ")}</p>`
      : "";
    const nomes = [...new Set(precos.map((row) => row.nomeProduto).filter(Boolean))];
    const anos = [...new Set(precos.map((row) => String(row.dataEmissao).slice(0, 4)).filter((ano) => /^\d{4}$/.test(ano)))].sort();
    const meses = [
      ["", "Todos os meses"],
      ["01", "Janeiro"], ["02", "Fevereiro"], ["03", "Março"], ["04", "Abril"],
      ["05", "Maio"], ["06", "Junho"], ["07", "Julho"], ["08", "Agosto"],
      ["09", "Setembro"], ["10", "Outubro"], ["11", "Novembro"], ["12", "Dezembro"]
    ];
    return `
      <section class="price-panel" id="price-history">
        <h3>Histórico de preços praticados</h3>
        ${banner}
        <div class="price-filters">
          <label>Produto<select id="price-product">${nomes.map((nome, index) => `<option value="${escapeHtml(nome)}"${index === 0 ? " selected" : ""}>${escapeHtml(nome)}</option>`).join("")}</select></label>
          <label>Mês<select id="price-month">${meses.map(([valor, rotulo]) => `<option value="${valor}">${rotulo}</option>`).join("")}</select></label>
          <label>Ano<select id="price-year"><option value="">Todos os anos</option>${anos.map((ano) => `<option value="${ano}">${ano}</option>`).join("")}</select></label>
        </div>
        <div id="price-chart"></div>
        <p id="price-summary" class="price-summary"></p>
      </section>`;
  }

  function ligarPrecos(client) {
    const painel = document.getElementById("price-history");
    if (!painel) return;
    const desenhar = () => desenharPrecos(client);
    painel.querySelectorAll("select").forEach((select) => select.addEventListener("change", desenhar));
    desenhar();
  }

  function desenharPrecos(client) {
    const chart = document.getElementById("price-chart");
    const summary = document.getElementById("price-summary");
    const produto = document.getElementById("price-product");
    const mes = document.getElementById("price-month");
    const ano = document.getElementById("price-year");
    if (!chart || !summary || !produto || !mes || !ano) return;
    const pontos = precosDoCliente(client).filter((row) => {
      if (produto.value && row.nomeProduto !== produto.value) return false;
      const data = String(row.dataEmissao || "");
      if (ano.value && !data.startsWith(ano.value)) return false;
      if (mes.value && data.slice(5, 7) !== mes.value) return false;
      return true;
    }).sort((a, b) => a.dataEmissao.localeCompare(b.dataEmissao));
    if (!pontos.length) {
      chart.innerHTML = '<p class="empty">Nenhum preço nesse recorte.</p>';
      summary.textContent = "";
      return;
    }
    const valores = pontos.map((ponto) => ponto.valorUnitario);
    const minimo = Math.min(...valores);
    const maximo = Math.max(...valores);
    chart.innerHTML = graficoPreco(pontos, minimo, maximo);
    summary.innerHTML = `<span>Menor valor <strong class="price-min-label">${money(minimo)}</strong></span><span>Maior valor <strong class="price-max-label">${money(maximo)}</strong></span>`;
  }

  function graficoPreco(pontos, minimo, maximo) {
    const largura = 640;
    const altura = 200;
    const margem = 28;
    const tempos = pontos.map((ponto) => Date.parse(ponto.dataEmissao) || 0);
    const inicio = Math.min(...tempos);
    const fim = Math.max(...tempos);
    const faixa = fim - inicio || 1;
    const amplitude = maximo - minimo || 1;
    const coords = pontos.map((ponto, indice) => {
      const tempo = Date.parse(ponto.dataEmissao) || inicio;
      let x = fim === inicio ? largura / 2 : margem + ((tempo - inicio) / faixa) * (largura - margem * 2);
      const repetido = pontos.filter((outro, posicao) => outro.dataEmissao === ponto.dataEmissao && posicao < indice).length;
      x += repetido * 10;
      const y = margem + (1 - (ponto.valorUnitario - minimo) / amplitude) * (altura - margem * 2);
      return { ...ponto, x, y };
    });
    const linha = coords.map((ponto) => `${ponto.x.toFixed(1)},${ponto.y.toFixed(1)}`).join(" ");
    const marcas = coords.map((ponto) => {
      const classes = ["price-dot"];
      if (ponto.valorUnitario === minimo) classes.push("is-min");
      if (ponto.valorUnitario === maximo) classes.push("is-max");
      return `<circle class="${classes.join(" ")}" cx="${ponto.x.toFixed(1)}" cy="${ponto.y.toFixed(1)}" r="4"><title>${escapeHtml(formatDate(ponto.dataEmissao))} · ${escapeHtml(money(ponto.valorUnitario))}</title></circle>`;
    }).join("");
    return `<svg class="price-chart" viewBox="0 0 ${largura} ${altura}" role="img" aria-label="Preço unitário nas datas de emissão"><line class="price-axis" x1="${margem}" y1="${altura - margem}" x2="${largura - margem}" y2="${altura - margem}"></line><polyline class="price-line" points="${linha}"></polyline>${marcas}</svg>`;
  }

  function referenciaBi() {
    const iso = (mock && mock.TODAY) || "2026-09-22";
    const [ano, mes, dia] = iso.split("-").map(Number);
    return new Date(ano, mes - 1, dia);
  }

  function intervaloBi() {
    const hoje = referenciaBi();
    const iso = (data) => {
      const m = String(data.getMonth() + 1).padStart(2, "0");
      const d = String(data.getDate()).padStart(2, "0");
      return `${data.getFullYear()}-${m}-${d}`;
    };
    if (state.biPeriodo === "mes") {
      const inicio = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
      return { inicio: iso(inicio), fim: iso(hoje) };
    }
    if (state.biPeriodo === "ano") {
      return { inicio: `${hoje.getFullYear()}-01-01`, fim: iso(hoje) };
    }
    if (state.biPeriodo === "custom") {
      const inicio = document.getElementById("bi-inicio");
      const fim = document.getElementById("bi-fim");
      return {
        inicio: (inicio && inicio.value) || "2000-01-01",
        fim: (fim && fim.value) || iso(hoje)
      };
    }
    const inicio = new Date(hoje);
    inicio.setFullYear(inicio.getFullYear() - 1);
    return { inicio: iso(inicio), fim: iso(hoje) };
  }

  function clientePorNomus(idCliente) {
    const chave = String(idCliente);
    return state.clients.find((client) => String(client.nomusId) === chave || String(client.id).replace(/^nomus-/, "") === chave);
  }

  function linhasFaturadas() {
    const { inicio, fim } = intervaloBi();
    const dentro = (data) => data && data >= inicio && data <= fim;
    if (state.historicoPrecos.length) {
      return state.historicoPrecos.filter((row) => dentro(String(row.dataEmissao || ""))).map((row) => {
        const quantidade = Number(row.quantidade) || 0;
        const unitario = Number(row.valorUnitario) || 0;
        const client = clientePorNomus(row.idCliente);
        return {
          data: String(row.dataEmissao || ""),
          produto: String(row.nomeProduto || "Produto"),
          idProduto: row.idProduto,
          quantidade,
          valor: quantidade * unitario,
          clienteId: client ? client.id : `nomus-${row.idCliente}`,
          cliente: client ? (client.nomeFantasia || client.razaoSocial) : `Cliente ${row.idCliente}`,
          uf: client ? String(client.uf || "—") : "—",
          pedido: ""
        };
      });
    }
    const linhas = [];
    state.clients.forEach((client) => {
      (client.pedidos || []).forEach((pedido) => {
        if (!dentro(String(pedido.data || ""))) return;
        linhas.push({
          data: String(pedido.data || ""),
          produto: String(pedido.item || "Pedido"),
          idProduto: null,
          quantidade: Number(pedido.quantidade) || 0,
          valor: Number(pedido.valor) || 0,
          clienteId: client.id,
          cliente: client.nomeFantasia || client.razaoSocial,
          uf: String(client.uf || "—"),
          pedido: String(pedido.codigo || "")
        });
      });
    });
    return linhas;
  }

  function agrupar(linhas, chave, campo) {
    const mapa = new Map();
    linhas.forEach((linha) => {
      const id = String(linha[chave] || "—");
      if (!mapa.has(id)) mapa.set(id, { chave: id, valor: 0, quantidade: 0, rotulo: linha[campo] || id });
      const grupo = mapa.get(id);
      grupo.valor += linha.valor;
      grupo.quantidade += linha.quantidade;
    });
    return [...mapa.values()];
  }

  function barrasBi(itens, formato) {
    if (!itens.length) return '<p class="empty">Sem faturamento neste período.</p>';
    const topo = itens[0][formato === "qtd" ? "quantidade" : "valor"] || 1;
    return itens.slice(0, 8).map((item) => {
      const medida = formato === "qtd" ? item.quantidade : item.valor;
      const largura = Math.max(4, Math.round((medida / (topo || 1)) * 100));
      const texto = formato === "qtd"
        ? `${item.quantidade.toLocaleString("pt-BR")} un`
        : `${money(item.valor)}${formato === "pct" ? ` · ${item.pct}%` : ""}`;
      return `<button type="button" class="bi-bar" data-action="bi-drill" data-kind="${escapeHtml(item.kind)}" data-key="${escapeHtml(item.chave)}"><span class="bi-bar-rotulo">${escapeHtml(item.rotulo)}</span><span class="bi-bar-valor">${escapeHtml(texto)}</span><span class="bi-bar-trilho"><span class="bi-bar-fill" style="width:${largura}%"></span></span></button>`;
    }).join("");
  }

  function renderPainelBi() {
    const grid = document.getElementById("bi-grid");
    if (!grid) return;
    document.querySelectorAll("[data-action='bi-periodo']").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.periodo === state.biPeriodo));
    });
    const linhas = linhasFaturadas();
    const total = linhas.reduce((soma, linha) => soma + linha.valor, 0) || 1;
    const porProduto = agrupar(linhas, "produto", "produto")
      .map((item) => ({ ...item, kind: "produto" }))
      .sort((a, b) => b.valor - a.valor);
    const porVolume = [...porProduto].sort((a, b) => b.quantidade - a.quantidade);
    const porUf = agrupar(linhas, "uf", "uf")
      .map((item) => ({ ...item, kind: "uf" }))
      .sort((a, b) => b.valor - a.valor);
    const porCliente = agrupar(linhas, "clienteId", "cliente")
      .map((item) => ({ ...item, kind: "cliente", pct: Math.round((item.valor / total) * 1000) / 10 }))
      .sort((a, b) => b.valor - a.valor);
    state.biCache = { linhas, porProduto, porVolume, porUf, porCliente };
    grid.innerHTML = [
      ["Faturamento por produto", barrasBi(porProduto, "valor")],
      ["Volume de fabricação", barrasBi(porVolume, "qtd")],
      ["Regiões / estados", barrasBi(porUf, "valor")],
      ["Maiores clientes", barrasBi(porCliente, "pct")]
    ].map(([titulo, corpo]) => `<article class="bi-card"><h3>${titulo}</h3>${corpo}</article>`).join("");
  }

  function pedidosDoCliente(linha) {
    const client = state.clients.find((item) => item.id === linha.clienteId);
    if (!client) return linha.pedido || "—";
    const nomes = String(linha.produto || "").toLowerCase();
    const codigos = (client.pedidos || [])
      .filter((pedido) => pedido.data === linha.data && (!nomes || String(pedido.item || "").toLowerCase().includes(nomes.slice(0, 24))))
      .map((pedido) => pedido.codigo);
    if (codigos.length) return codigos.join(", ");
    const mesmoDia = (client.pedidos || []).filter((pedido) => pedido.data === linha.data).map((pedido) => pedido.codigo);
    return mesmoDia.join(", ") || linha.pedido || "—";
  }

  function abrirDrillBi(kind, key) {
    const dialog = document.getElementById("dialog-bi");
    const titulo = document.getElementById("bi-dialog-titulo");
    const corpo = document.getElementById("bi-dialog-corpo");
    if (!dialog || !state.biCache) return;
    const linhas = state.biCache.linhas.filter((linha) => {
      if (kind === "produto") return linha.produto === key;
      if (kind === "uf") return linha.uf === key;
      return linha.clienteId === key;
    });
    const rotulo = kind === "cliente"
      ? (linhas[0] && linhas[0].cliente) || key
      : key;
    titulo.textContent = rotulo;
    if (kind === "uf") {
      const clientes = new Map();
      linhas.forEach((linha) => {
        if (!clientes.has(linha.clienteId)) clientes.set(linha.clienteId, { nome: linha.cliente, produtos: new Map() });
        const grupo = clientes.get(linha.clienteId).produtos;
        grupo.set(linha.produto, (grupo.get(linha.produto) || 0) + linha.valor);
      });
      corpo.innerHTML = `<table class="bi-tabela"><thead><tr><th>Cliente</th><th>Produtos</th><th>Valor</th></tr></thead><tbody>${[...clientes.values()].map((cliente) => {
        const produtos = [...cliente.produtos.entries()].map(([nome, valor]) => `${escapeHtml(nome)} (${escapeHtml(money(valor))})`).join("<br>");
        const total = [...cliente.produtos.values()].reduce((soma, valor) => soma + valor, 0);
        return `<tr><td>${escapeHtml(cliente.nome)}</td><td>${produtos}</td><td>${escapeHtml(money(total))}</td></tr>`;
      }).join("")}</tbody></table>`;
    } else if (kind === "cliente") {
      const mix = agrupar(linhas, "produto", "produto").sort((a, b) => b.valor - a.valor);
      corpo.innerHTML = `<table class="bi-tabela"><thead><tr><th>Produto</th><th>Quantidade</th><th>Valor</th></tr></thead><tbody>${mix.map((item) => `<tr><td>${escapeHtml(item.rotulo)}</td><td>${item.quantidade.toLocaleString("pt-BR")}</td><td>${escapeHtml(money(item.valor))}</td></tr>`).join("")}</tbody></table>`;
    } else {
      corpo.innerHTML = `<table class="bi-tabela"><thead><tr><th>Cliente</th><th>Quantidade</th><th>Valor</th><th>Pedidos</th></tr></thead><tbody>${linhas.map((linha) => `<tr><td>${escapeHtml(linha.cliente)}</td><td>${linha.quantidade.toLocaleString("pt-BR")}</td><td>${escapeHtml(money(linha.valor))}</td><td>${escapeHtml(pedidosDoCliente(linha))}</td></tr>`).join("")}</tbody></table>`;
    }
    if (typeof dialog.showModal === "function") dialog.showModal();
  }

  function renderProducts() {
    const consulta = fold(state.productQuery);
    const linha = state.productLine;
    const lista = state.products.filter((product) => {
      if (linha !== "todos" && product.familia !== linha) return false;
      if (!consulta) return true;
      return fold(`${product.codigo} ${product.descricao}`).includes(consulta);
    });
    const count = document.getElementById("product-count");
    if (count) count.textContent = `${lista.length} produto${lista.length === 1 ? "" : "s"}`;
    document.querySelectorAll("#product-lines [data-line]").forEach((button) => {
      button.setAttribute("aria-selected", String(button.dataset.line === linha));
    });
    const root = document.getElementById("product-list");
    if (root) {
      root.innerHTML = lista.length
        ? lista.map(productCard).join("")
        : '<p class="empty">Nenhum produto nesse recorte.</p>';
    }
    const fonte = document.getElementById("produtos-fonte");
    if (fonte) {
      fonte.textContent = state.produtosFonte === "arquivo"
        ? "Catálogo lido do arquivo local da consulta Nomus. Não é integração ao vivo."
        : "Catálogo simulado. O arquivo da consulta Nomus não abriu nesta sessão.";
    }
  }

  function productCard(product) {
    const status = product.vendavel ? "À venda" : "Fora de linha";
    return `<article class="product-card" data-line="${escapeHtml(product.familia)}"><p class="product-code">${escapeHtml(product.codigo || "Sem código")}</p><h3>${escapeHtml(product.descricao)}</h3><p class="client-meta">${escapeHtml(product.familia || "Sem família")} · ${escapeHtml(product.grupo || "Sem grupo")} · ${escapeHtml(product.unidade || "UN")}</p><span class="chip">${escapeHtml(status)}</span></article>`;
  }

  function showScreen(name) {
    document.getElementById("screen-auth").hidden = name !== "auth";
    document.getElementById("screen-app").hidden = name !== "app";
  }

  function showView(view) {
    state.view = view;
    document.getElementById("view-dashboard").hidden = view !== "dashboard";
    document.getElementById("view-products").hidden = view !== "products";
    document.getElementById("view-atividades").hidden = view !== "atividades";
    document.getElementById("view-clients").hidden = view !== "clients";
    const titulos = { dashboard: "Dashboard", products: "Produtos", atividades: "Atividades", clients: "Carteira de clientes" };
    document.getElementById("page-title").textContent = titulos[view] || "Dashboard";
    if (view === "products") {
      renderPainelBi();
      renderProducts();
    }
    if (view === "atividades") carregarAtividades();
    document.querySelectorAll("[data-action='show-view']").forEach((button) => {
      if (button.dataset.view === view) button.setAttribute("aria-current", "page");
      else button.removeAttribute("aria-current");
    });
    closeDrawer();
  }

  function dataValida(valor) {
    const data = valor instanceof Date ? valor : new Date(valor);
    return Number.isNaN(data.getTime()) ? null : data;
  }

  function maiorData(lista) {
    let maior = null;
    (lista || []).forEach((item) => {
      if (item && maior === null) maior = item;
      else if (item && item > maior) maior = item;
    });
    return maior;
  }

  function ultimoContatoCliente(client) {
    const manuais = state.atividades
      .filter((atividade) => String(atividade.nomusId) === String(client.nomusId || client.id))
      .map((atividade) => dataValida(atividade.data || atividade.dataHora || atividade.createdAt));
    const orcamentos = (client.orcamentos || []).map((orcamento) => dataValida(orcamento.data));
    const pedidos = (client.pedidos || []).map((pedido) => dataValida(pedido.data));
    return maiorData(manuais.concat(orcamentos, pedidos).filter(Boolean));
  }

  function resumoUltimoContato(data) {
    if (!data) {
      return { dias: null, texto: "Sem registro", classe: "badge badge-danger", status: "Sem contato" };
    }
    const iso = `${data.getFullYear()}-${String(data.getMonth() + 1).padStart(2, "0")}-${String(data.getDate()).padStart(2, "0")}`;
    const dias = daysSince(iso);
    if (dias <= 0) return { dias: 0, texto: "Hoje", classe: "badge", status: "Em dia" };
    const classe = dias > 30 ? "badge badge-danger" : dias > 15 ? "badge badge-warning" : "badge";
    const status = dias > 30 ? "Sem contato > 30 dias" : dias > 15 ? "Sem contato > 15 dias" : "Recente";
    return { dias, texto: `Há ${dias} dias`, classe, status };
  }

  function passaFiltroAtividade(resumo) {
    const filtro = state.atividadesFiltro;
    if (filtro === "30d") return resumo.dias === null || resumo.dias > 30;
    if (filtro === "15d") return resumo.dias === null || resumo.dias > 15;
    return true;
  }

  async function carregarAtividades() {
    try {
      const resposta = await fetch("/api/atividades");
      if (resposta.ok) {
        const data = await resposta.json();
        state.atividades = data || [];
      }
    } catch (erro) {
      state.atividades = state.atividades || [];
    }
    renderAtividades();
  }

  function renderAtividades() {
    const total = document.getElementById("total-clientes-atividades");
    const corpo = document.getElementById("lista-atividades-tbody");
    if (!corpo) return;
    if (total) total.textContent = String(state.clients.length);
    document.querySelectorAll("#view-atividades [data-filter]").forEach((botao) => {
      botao.classList.toggle("active", botao.dataset.filter === state.atividadesFiltro);
    });
    const linhas = state.clients.map((client) => {
      const resumo = resumoUltimoContato(ultimoContatoCliente(client));
      return { client, resumo };
    }).filter((item) => passaFiltroAtividade(item.resumo));
    corpo.innerHTML = linhas.length
      ? linhas.map(({ client, resumo }) => `<tr><td>${escapeHtml(client.razaoSocial)}</td><td>${escapeHtml(client.cidade || "—")}/${escapeHtml(client.uf || "—")}</td><td>${escapeHtml(client.contato || "—")}</td><td>${escapeHtml(resumo.texto)}</td><td><span class="${resumo.classe}">${escapeHtml(resumo.status)}</span></td><td><button type="button" class="btn btn-small" data-action="registrar-contato" data-id="${escapeHtml(client.id)}">+ Registrar Contato</button></td></tr>`).join("")
      : '<tr><td colspan="6">Nenhum cliente neste filtro.</td></tr>';
    renderFormularioAtividade();
  }

  function renderFormularioAtividade() {
    const caixa = document.getElementById("atividades-form-container");
    if (!caixa) return;
    const client = state.atividadeClienteId ? getClient(state.atividadeClienteId) : null;
    if (!client) {
      caixa.hidden = true;
      caixa.innerHTML = "";
      return;
    }
    caixa.hidden = false;
    caixa.innerHTML = `<form id="form-atividade" class="inline-atividade"><p class="eyebrow">Registrar contato · ${escapeHtml(client.razaoSocial)}</p><label>Canal<select name="canal" required><option value="WhatsApp">WhatsApp</option><option value="E-mail">E-mail</option><option value="Ligação">Ligação</option></select></label><label>Resultado<select name="resultado" required><option value="Sucesso">Sucesso</option><option value="Sem sucesso">Sem sucesso</option></select></label><label>Observação<textarea name="observacao" rows="3"></textarea></label><div class="form-actions"><button type="submit" class="btn btn-accent">Salvar contato</button><button type="button" class="btn" data-action="cancelar-contato">Cancelar</button></div><p id="atividade-feedback" class="footnote" hidden></p></form>`;
  }

  async function salvarAtividade(form) {
    const client = getClient(state.atividadeClienteId);
    if (!client) return;
    const dados = new FormData(form);
    const payload = {
      nomusId: client.nomusId || client.id,
      tipo: dados.get("canal"),
      status: dados.get("resultado"),
      observacao: String(dados.get("observacao") || "").trim(),
      usuario: state.usuario || (state.session && state.session.nome) || "Natália"
    };
    const feedback = document.getElementById("atividade-feedback");
    try {
      const resposta = await fetch("/api/atividades", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      const corpo = await resposta.json().catch(() => ({}));
      if (!resposta.ok || corpo.sucesso !== true) {
        if (feedback) {
          feedback.hidden = false;
          feedback.textContent = "Não foi possível registrar o contato.";
        }
        return;
      }
      state.atividades.push({
        ...payload,
        data: TODAY,
        createdAt: new Date().toISOString()
      });
      state.atividadeClienteId = null;
      renderAtividades();
      toast("Contato registrado.");
    } catch (erro) {
      if (feedback) {
        feedback.hidden = false;
        feedback.textContent = "Não foi possível registrar o contato.";
      }
    }
  }

  function showRanking(ranking) {
    if (!RANKINGS[ranking]) return;
    state.ranking = ranking;
    if (state.view !== "clients") showView("clients");
    else closeDrawer();
    renderClientList();
  }

  function setAuthTab(tab) {
    const isLogin = tab !== "register";
    document.getElementById("form-login").hidden = !isLogin;
    document.getElementById("form-register").hidden = isLogin;
    document.getElementById("tab-login").setAttribute("aria-selected", String(isLogin));
    document.getElementById("tab-register").setAttribute("aria-selected", String(!isLogin));
    setFeedback("");
  }

  function setFeedback(message) {
    const element = document.getElementById("auth-feedback");
    element.textContent = message;
    element.hidden = !message;
  }

  function toast(message) {
    const element = document.getElementById("toast");
    element.textContent = message;
    element.hidden = false;
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      element.hidden = true;
    }, 3400);
  }

  function hideToast() {
    window.clearTimeout(toastTimer);
    document.getElementById("toast").hidden = true;
  }

  function initials(nome) {
    const parts = String(nome || "").trim().split(/\s+/).filter(Boolean);
    const first = parts[0] ? parts[0][0] : "";
    const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
    return `${first}${last}`.toUpperCase() || "CR";
  }

  function perfilLabel(perfil) {
    if (perfil === "administrador") return "Administrador";
    if (perfil === "vendedor") return "Vendedor";
    return "Vendedora";
  }

  function renderProfile() {
    const session = state.session;
    if (!session) return;
    document.getElementById("profile-name").textContent = session.nome;
    document.getElementById("profile-initials").textContent = initials(session.nome);
    document.getElementById("profile-role").textContent = `${perfilLabel(session.perfil)} · EHE Indústria`;
    document.getElementById("session-email").textContent = session.email;
    document.getElementById("performance-title").textContent = `Minha Performance (${session.nome})`;
  }

  const CLIENTS_KEY = "crmer.clients";
  const EDITS_KEY = "crmer.clientEdits";
  const DADOS_URL = "backend/output/dados_ehe.json";
  const CARTEIRA_URL = "backend/output/carteira_natalia.json";

  function readStorage(key) {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) return null;
      return JSON.parse(raw);
    } catch (error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (error) {
      /* A ficha segue em memória se o navegador recusar o armazenamento. */
    }
  }

  function normalizarCliente(client) {
    const ranking = RANKINGS[client.ranking] ? client.ranking : "contato";
    return cloneClient({
      ...client,
      ranking,
      linhas: Array.isArray(client.linhas) ? client.linhas : [],
      pedidos: Array.isArray(client.pedidos) ? client.pedidos : [],
      orcamentos: Array.isArray(client.orcamentos) ? client.orcamentos : [],
      anotacoes: String(client.anotacoes || ""),
      proximoContato: String(client.proximoContato || "")
    });
  }

  function lerEdicoes() {
    const stored = readStorage(EDITS_KEY);
    if (!stored || typeof stored !== "object" || Array.isArray(stored)) return {};
    return stored;
  }

  function aplicarEdicoes(clients) {
    const edits = lerEdicoes();
    return clients.map((client) => {
      const edit = edits[client.id];
      if (!edit || typeof edit !== "object") return client;
      return {
        ...client,
        anotacoes: typeof edit.anotacoes === "string" ? edit.anotacoes : client.anotacoes,
        proximoContato: typeof edit.proximoContato === "string" ? edit.proximoContato : client.proximoContato
      };
    });
  }

  function clientesManuais(baseIds) {
    const stored = readStorage(CLIENTS_KEY);
    if (!Array.isArray(stored)) return [];
    return stored
      .filter((client) => client && client.origemManual && client.id && !baseIds.has(client.id))
      .map(normalizarCliente);
  }

  function persistirCarteira() {
    writeStorage(CLIENTS_KEY, state.clients);
    const edits = lerEdicoes();
    state.clients.forEach((client) => {
      if (!client.origemManual && edits[client.id]) {
        edits[client.id] = {
          anotacoes: client.anotacoes,
          proximoContato: client.proximoContato
        };
      }
    });
    writeStorage(EDITS_KEY, edits);
  }

  function gravarEdicao(client) {
    const edits = lerEdicoes();
    edits[client.id] = {
      anotacoes: String(client.anotacoes || ""),
      proximoContato: String(client.proximoContato || "")
    };
    writeStorage(EDITS_KEY, edits);
    persistirCarteira();
  }

  function normalizarProduto(product) {
    const familia = String(product.familia || product.linha || "");
    return {
      id: product.id,
      codigo: String(product.codigo || ""),
      descricao: String(product.descricao || "Produto sem descrição"),
      familia,
      grupo: String(product.grupo || familia || ""),
      unidade: String(product.unidade || "UN"),
      vendavel: product.vendavel !== false
    };
  }

  function listaDeClientes(payload) {
    const lista = Array.isArray(payload.clientes) ? payload.clientes : payload.clients;
    if (!Array.isArray(lista)) return null;
    return lista.filter((client) => client && client.id && client.razaoSocial).map(normalizarCliente);
  }

  function listaDeProdutos(payload) {
    let lista = payload.produtos;
    if (lista && !Array.isArray(lista) && typeof lista === "object") lista = Object.values(lista).flat();
    if ((!Array.isArray(lista) || !lista.length) && payload.produtosPorFamilia && typeof payload.produtosPorFamilia === "object") {
      lista = Object.values(payload.produtosPorFamilia).flat();
    }
    if (!Array.isArray(lista)) return null;
    return lista.filter((product) => product && (product.codigo || product.descricao)).map(normalizarProduto);
  }

  function distribuirPrecos(clients, historico) {
    if (!Array.isArray(historico) || !historico.length) return clients;
    const mapa = new Map();
    historico.forEach((row) => {
      const chave = String(row.idCliente);
      if (!mapa.has(chave)) mapa.set(chave, []);
      mapa.get(chave).push(row);
    });
    return clients.map((client) => {
      const linhas = mapa.get(String(client.nomusId)) || mapa.get(String(client.id).replace(/^nomus-/, "")) || mapa.get(String(client.id));
      return linhas ? { ...client, precos: linhas } : client;
    });
  }

  async function buscarJson(url) {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(url, { cache: "no-store", signal: controller.signal });
      if (!response.ok) return null;
      const payload = await response.json();
      if (!payload || typeof payload !== "object") return null;
      return payload;
    } catch (error) {
      return null;
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function carregarCarteira() {
    const dados = await buscarJson(DADOS_URL);
    const legado = dados ? null : await buscarJson(CARTEIRA_URL);
    const payload = dados || legado;
    const arquivo = payload ? listaDeClientes(payload) : null;
    const base = arquivo || mock.clients.map(normalizarCliente);
    state.carteiraFonte = arquivo ? "arquivo" : "simulada";
    const produtosArquivo = payload ? listaDeProdutos(payload) : null;
    state.products = produtosArquivo && produtosArquivo.length ? produtosArquivo : (mock.produtos || []).map(normalizarProduto);
    state.produtosFonte = produtosArquivo && produtosArquivo.length ? "arquivo" : "simulada";
    const ids = new Set(base.map((client) => client.id));
    state.historicoPrecos = payload && Array.isArray(payload.historico_precos) ? payload.historico_precos : [];
    const comPrecos = distribuirPrecos(base, state.historicoPrecos);
    state.clients = aplicarEdicoes(clientesManuais(ids).concat(comPrecos));
    writeStorage(CLIENTS_KEY, state.clients);
  }

  async function enterApp(session) {
    state.session = session;
    renderProfile();
    try {
      await carregarCarteira();
    } catch (error) {
      state.clients = mock.clients.map(normalizarCliente);
      state.products = (mock.produtos || []).map(normalizarProduto);
      state.carteiraFonte = "simulada";
      state.produtosFonte = "simulada";
      state.historicoPrecos = [];
    }
    showScreen("app");
    showView("dashboard");
    renderDashboard();
    renderClientList();
  }

  function logout() {
    closeDrawer();
    clearSearch();
    hideToast();
    auth.clearSession();
    state.session = null;
    document.getElementById("form-login").reset();
    document.getElementById("form-register").reset();
    setAuthTab("login");
    showScreen("auth");
  }

  function handleLogin(form) {
    const data = new FormData(form);
    const identificador = String(data.get("identificador") || "").trim();
    const senha = String(data.get("senha") || "");
    if (!identificador || !senha.trim()) {
      setFeedback("Informe e-mail ou usuário e a senha para entrar.");
      return;
    }
    let session = null;
    try {
      session = auth.login(identificador, senha);
    } catch (error) {
      setFeedback(error.message || "Não foi possível entrar.");
      return;
    }
    if (!session) {
      setFeedback("E-mail, usuário ou senha não conferem.");
      return;
    }
    enterApp(session);
    toast(`Sessão aberta. Olá, ${session.nome}.`);
  }

  function handleRegister(form) {
    const data = new FormData(form);
    const nome = String(data.get("nome") || "").trim();
    const email = String(data.get("email") || "").trim();
    const senha = String(data.get("senha") || "");
    const confirmar = String(data.get("confirmar") || "");
    const perfil = String(data.get("perfil") || "vendedora");
    if (!nome || !email || !senha) {
      setFeedback("Preencha nome, e-mail e senha.");
      return;
    }
    if (!email.includes("@") || email.startsWith("@") || email.endsWith("@")) {
      setFeedback("Informe um e-mail válido para o cadastro.");
      return;
    }
    const faltas = auth.validarSenha(senha);
    if (faltas.length) {
      setFeedback(`A senha precisa de ${faltas.join(", ")}.`);
      refreshPasswordFeedback();
      return;
    }
    if (senha !== confirmar) {
      setFeedback("As senhas não coincidem.");
      refreshPasswordFeedback();
      return;
    }
    let session = null;
    try {
      session = auth.register({ nome, email, password: senha, perfil });
    } catch (error) {
      setFeedback(error.message || "Não foi possível criar a conta.");
      return;
    }
    enterApp(session);
    toast(`Conta de ${session.nome} gravada neste navegador.`);
  }

  function handleNotes(form) {
    const client = getClient(state.drawerId);
    if (!client) return;
    const data = new FormData(form);
    client.anotacoes = String(data.get("anotacoes") || "").trim();
    client.proximoContato = String(data.get("proximoContato") || "");
    gravarEdicao(client);
    renderDashboard();
    renderClientList();
    if (client.ranking === "contato" && client.proximoContato > TODAY) {
      toast(`Contato de ${client.razaoSocial} reagendado para ${formatDate(client.proximoContato)}.`);
      return;
    }
    toast(`Anotação salva na ficha de ${client.razaoSocial}.`);
  }

  function handleCreate(form) {
    const data = new FormData(form);
    const razaoSocial = String(data.get("razaoSocial") || "").trim();
    const contato = String(data.get("contato") || "").trim();
    const cidade = String(data.get("cidade") || "").trim();
    const error = form.querySelector(".form-feedback");
    if (!razaoSocial || !contato || !cidade) {
      error.textContent = "Preencha razão social, contato e cidade.";
      error.hidden = false;
      return;
    }
    const ranking = String(data.get("ranking") || "");
    if (!RANKINGS[ranking]) return;
    const linha = LINHAS.includes(data.get("linha")) ? String(data.get("linha")) : "Saneamento";
    const uf = UFS.includes(data.get("uf")) ? String(data.get("uf")) : "SP";
    let proximoContato = String(data.get("proximoContato") || "");
    if (ranking === "contato" && !proximoContato) proximoContato = TODAY;
    const client = {
      id: `cli-${Date.now()}`,
      razaoSocial,
      tipo: data.get("tipo") === "Instaladora" ? "Instaladora" : "Construtora",
      contato,
      cargo: "Contato comercial",
      nomeFantasia: razaoSocial,
      cnpj: "",
      email: "",
      telefone: "",
      whatsapp: "",
      cidade,
      uf,
      linhas: [linha],
      ranking,
      prioridade: "media",
      curva: ranking === "inativos" ? "B" : "",
      faturamento12m: 0,
      ultimaCompra: "",
      proximoContato,
      janelaSazonal: ranking === "sazonal" ? "Setembro e outubro" : "",
      resumo: "Cliente incluído manualmente. Histórico do Nomus ainda não vinculado.",
      anotacoes: String(data.get("anotacoes") || "").trim(),
      pedidos: [],
      orcamentos: [],
      origemManual: true
    };
    state.clients.unshift(client);
    persistirCarteira();
    state.ranking = ranking;
    if (state.view !== "clients") showView("clients");
    renderDashboard();
    renderClientList();
    openClient(client.id);
    toast(`${razaoSocial} entrou na fila ${RANKINGS[ranking].label}.`);
  }

  function fold(value) {
    return String(value || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase();
  }

  function onlyDigits(value) {
    return String(value || "").replace(/\D/g, "");
  }

  function clientMatches(client, query, queryDigits) {
    const text = [client.razaoSocial, client.nomeFantasia, client.cnpj, client.contato, client.telefone, client.whatsapp]
      .map(fold)
      .join(" ");
    if (query.length >= 2 && text.includes(query)) return true;
    if (queryDigits.length >= 3) {
      const haystack = [client.cnpj, client.telefone, client.whatsapp].map(onlyDigits).join(" ");
      if (haystack.includes(queryDigits)) return true;
    }
    return false;
  }

  function runSearch(raw) {
    const query = fold(String(raw || "").trim());
    const queryDigits = onlyDigits(raw);
    if (query.length < 2 && queryDigits.length < 3) return [];
    try {
      return state.clients.filter((client) => clientMatches(client, query, queryDigits)).slice(0, 8);
    } catch (error) {
      return [];
    }
  }

  function searchMeta(client) {
    return [client.nomeFantasia, client.cnpj, client.contato, client.telefone || client.whatsapp]
      .filter(Boolean)
      .join(" · ");
  }

  function closeSearchList() {
    const list = document.getElementById("quick-search-list");
    const input = document.getElementById("quick-search-input");
    if (!list || list.hidden) return false;
    list.hidden = true;
    list.innerHTML = "";
    if (input) {
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }
    state.searchIndex = -1;
    return true;
  }

  function clearSearch() {
    const input = document.getElementById("quick-search-input");
    if (input) input.value = "";
    closeSearchList();
  }

  function renderSearchResults(results) {
    const list = document.getElementById("quick-search-list");
    const input = document.getElementById("quick-search-input");
    if (!results.length) {
      list.innerHTML = '<li class="quick-search-empty">Nenhum cliente encontrado.</li>';
      list.hidden = false;
      input.setAttribute("aria-expanded", "true");
      input.removeAttribute("aria-activedescendant");
      state.searchIndex = -1;
      return;
    }
    if (state.searchIndex < 0 || state.searchIndex >= results.length) state.searchIndex = 0;
    list.innerHTML = results.map((client, index) => {
      const selected = index === state.searchIndex ? "true" : "false";
      return `<li role="presentation"><button type="button" class="search-option" role="option" id="search-opt-${index}" aria-selected="${selected}" data-action="open-client" data-id="${escapeHtml(client.id)}"><strong>${escapeHtml(client.razaoSocial)}</strong><small>${escapeHtml(searchMeta(client))}</small></button></li>`;
    }).join("");
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
    input.setAttribute("aria-activedescendant", `search-opt-${state.searchIndex}`);
  }

  function scheduleSearch() {
    window.clearTimeout(state.searchTimer);
    state.searchTimer = window.setTimeout(() => {
      const input = document.getElementById("quick-search-input");
      if (!input) return;
      if (!input.value.trim()) {
        closeSearchList();
        return;
      }
      state.searchIndex = 0;
      renderSearchResults(runSearch(input.value));
    }, 180);
  }

  function moveSearch(delta) {
    const input = document.getElementById("quick-search-input");
    const results = runSearch(input.value);
    if (!results.length) return;
    const current = state.searchIndex < 0 ? 0 : state.searchIndex;
    state.searchIndex = (current + delta + results.length) % results.length;
    renderSearchResults(results);
  }

  function openSearchResult() {
    const input = document.getElementById("quick-search-input");
    window.clearTimeout(state.searchTimer);
    const results = runSearch(input.value);
    if (!results.length) {
      renderSearchResults(results);
      toast("Nenhum cliente encontrado para essa busca.");
      return;
    }
    const chosen = results[state.searchIndex] || results[0];
    openClient(chosen.id);
  }

  function focusSearch() {
    if (document.getElementById("screen-app").hidden) return;
    const input = document.getElementById("quick-search-input");
    if (!input) return;
    input.focus();
    input.select();
  }

  function isTypingTarget(target) {
    if (!target || !target.tagName) return false;
    const tag = target.tagName;
    return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
  }

  function onGlobalKey(event) {
    const appHidden = document.getElementById("screen-app").hidden;
    if (appHidden) return;
    const key = event.key;
    if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "k") {
      event.preventDefault();
      focusSearch();
      return;
    }
    if (key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !isTypingTarget(event.target)) {
      event.preventDefault();
      focusSearch();
    }
  }

  function onSearchKey(event) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      moveSearch(1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      moveSearch(-1);
    }
  }

  function onEscapeSearch(event) {
    if (event.key !== "Escape") return;
    if (closeSearchList()) event.preventDefault();
  }

  function onClick(event) {
    if (event.target.matches("dialog.app-modal")) {
      fecharModal(event.target);
      return;
    }
    if (!event.target.closest("#quick-search")) closeSearchList();
    const element = event.target.closest("[data-action]");
    if (!element) return;
    const action = element.dataset.action;
    if (action === "toggle-password") togglePassword(element);
    if (action === "auth-tab") setAuthTab(element.dataset.tab);
    if (action === "show-view") showView(element.dataset.view);
    if (action === "bi-periodo") {
      state.biPeriodo = element.dataset.periodo || "12m";
      renderPainelBi();
    }
    if (action === "bi-drill") abrirDrillBi(element.dataset.kind, element.dataset.key);
    if (action === "filter-products") {
      state.productLine = element.dataset.line || "todos";
      renderProducts();
    }
    if (action === "show-ranking") showRanking(element.dataset.ranking);
    if (action === "open-client") openClient(element.dataset.id);
    if (action === "close-drawer") closeDrawer();
    if (action === "logout") logout();
    if (action === "filter-atividades") {
      state.atividadesFiltro = element.dataset.filter || "todos";
      renderAtividades();
    }
    if (action === "registrar-contato") {
      state.atividadeClienteId = element.dataset.id;
      renderFormularioAtividade();
    }
    if (action === "cancelar-contato") {
      state.atividadeClienteId = null;
      renderFormularioAtividade();
    }
    if (action === "new-client") abrirModalCliente();
    if (action === "editar-cliente") abrirModalCliente(state.drawerId);
    if (action === "fechar-modal-cliente") fecharModalCliente();
    if (action === "open-feedback") openFeedback();
    if (action === "close-feedback") closeFeedback();
    if (action === "open-changelog") openChangelog();
    if (action === "close-changelog") closeChangelog();
    if (action === "avancar-etapa") deslocarEtapa(element.dataset.id, 1);
    if (action === "voltar-etapa") deslocarEtapa(element.dataset.id, -1);
    if (action === "marcar-perdido") abrirPerda(element.dataset.id);
    if (action === "cancelar-perda") fecharPerda();
  }

  function onFunilDragStart(event) {
    const card = event.target.closest(".kanban-card");
    if (!card) return;
    event.dataTransfer.setData("text/plain", card.dataset.processoId || "");
    event.dataTransfer.effectAllowed = "move";
  }

  function onFunilDragOver(event) {
    if (!event.target.closest(".kanban-col")) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }

  function onFunilDrop(event) {
    const coluna = event.target.closest(".kanban-col");
    if (!coluna) return;
    event.preventDefault();
    const id = event.dataTransfer.getData("text/plain");
    moverEtapa(id, coluna.dataset.etapa);
  }

  function onPerdaCategoria(event) {
    if (event.target.id !== "perda-categoria") return;
    preencherMotivosPerda(event.target.value);
  }

  function onSubmit(event) {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (!["form-login", "form-register", "form-notes", "form-create", "form-search", "form-product-search", "form-feedback", "form-atividade", "form-perda", "form-cliente"].includes(form.id)) return;
    event.preventDefault();
    if (form.id === "form-login") handleLogin(form);
    if (form.id === "form-register") handleRegister(form);
    if (form.id === "form-notes") handleNotes(form);
    if (form.id === "form-create") handleCreate(form);
    if (form.id === "form-search") openSearchResult();
    if (form.id === "form-feedback") handleFeedback(form);
    if (form.id === "form-atividade") salvarAtividade(form);
    if (form.id === "form-perda") confirmarPerda(form);
    if (form.id === "form-cliente") salvarModalCliente(form);
  }

  function togglePassword(button) {
    const input = document.getElementById(button.getAttribute("aria-controls"));
    if (!input) return;
    const showing = input.type === "text";
    input.type = showing ? "password" : "text";
    button.setAttribute("aria-pressed", String(!showing));
    button.setAttribute("aria-label", showing ? "Mostrar senha" : "Ocultar senha");
    const open = button.querySelector(".icon-eye");
    const shut = button.querySelector(".icon-eye-off");
    if (open) open.hidden = !showing;
    if (shut) shut.hidden = showing;
    input.focus();
  }

  function refreshPasswordFeedback() {
    const senha = document.getElementById("register-senha");
    const confirmar = document.getElementById("register-confirmar");
    const match = document.getElementById("senha-match");
    if (!senha || !confirmar || !match) return;
    document.querySelectorAll("#senha-requisitos [data-rule]").forEach((item) => {
      const value = senha.value;
      const met = {
        tamanho: value.length >= 8,
        maiuscula: /[A-Z]/.test(value),
        numero: /[0-9]/.test(value),
        especial: /[!@#$%^&*(),.?":{}|<>_\-]/.test(value)
      }[item.dataset.rule];
      item.classList.toggle("is-met", Boolean(met));
    });
    if (!confirmar.value) {
      match.hidden = true;
      match.textContent = "";
      match.classList.remove("is-ok", "is-bad");
      confirmar.removeAttribute("aria-invalid");
      return;
    }
    const ok = senha.value === confirmar.value;
    match.hidden = false;
    match.textContent = ok ? "As senhas coincidem" : "As senhas não coincidem";
    match.classList.toggle("is-ok", ok);
    match.classList.toggle("is-bad", !ok);
    confirmar.setAttribute("aria-invalid", String(!ok));
  }

  const SUGESTOES_KEY = "crmer.sugestoes";
  const NOVIDADES_FALLBACK = [
    {
      versao: "1.4.0",
      data: "23/09/2026",
      solicitante: "Natália",
      itens: [
        "Local de entrega da obra na linha do pedido faturado.",
        "Transportadora vinculada à NF-e do pedido.",
        "Follow-ups de orçamento a partir dos processos de vendas."
      ]
    }
  ];

  function moduloAtual() {
    if (state.drawerId) return "Ficha do Cliente";
    if (state.view === "products") return "Produtos";
    if (state.view === "dashboard") return "Dashboard";
    return "Ficha do Cliente";
  }

  function openFeedback() {
    if (!state.session) return;
    const form = document.getElementById("form-feedback");
    const erro = document.getElementById("feedback-error");
    form.reset();
    form.modulo.value = moduloAtual();
    erro.hidden = true;
    erro.textContent = "";
    abrirModal(document.getElementById("modal-feedback"));
  }

  function closeFeedback() {
    fecharModal(document.getElementById("modal-feedback"));
  }

  function autorAtivo() {
    const nome = state.session && state.session.nome;
    return String(nome || "Natália").trim() || "Natália";
  }

  function dataLocalCurta(iso) {
    const momento = new Date(iso);
    if (Number.isNaN(momento.getTime())) return "";
    const parte = (valor) => String(valor).padStart(2, "0");
    return `${momento.getFullYear()}-${parte(momento.getMonth() + 1)}-${parte(momento.getDate())} ${parte(momento.getHours())}:${parte(momento.getMinutes())}`;
  }

  function lerSugestoesLocais() {
    const stored = readStorage(SUGESTOES_KEY);
    return Array.isArray(stored) ? stored : [];
  }

  function baixarSugestao(item, carimbo) {
    const blob = new Blob([JSON.stringify(item, null, 2) + "\n"], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `sugestao_${carimbo}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function guardarSugestaoLocal(payload) {
    const carimbo = Date.now();
    const item = {
      id: carimbo,
      data: dataLocalCurta(payload.data),
      autor: payload.autor,
      modulo: payload.modulo,
      tipo: payload.tipo,
      descricao: payload.descricao,
      prioridade: payload.prioridade,
      status: "Pendente",
      resposta_tecnica: ""
    };
    const lista = lerSugestoesLocais();
    lista.push(item);
    writeStorage(SUGESTOES_KEY, lista);
    baixarSugestao(item, carimbo);
    return item;
  }

  async function handleFeedback(form) {
    const erro = document.getElementById("feedback-error");
    const descricao = String(new FormData(form).get("descricao") || "").trim();
    if (!descricao) {
      erro.textContent = "Descreva o que precisa mudar na rotina.";
      erro.hidden = false;
      return;
    }
    const dados = new FormData(form);
    const payload = {
      modulo: String(dados.get("modulo") || "Outro"),
      tipo: String(dados.get("tipo") || ""),
      descricao,
      prioridade: String(dados.get("prioridade") || "Média"),
      data: new Date().toISOString(),
      autor: autorAtivo()
    };
    erro.hidden = true;
    let enviou = false;
    try {
      const controller = new AbortController();
      const timer = window.setTimeout(() => controller.abort(), 4000);
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      window.clearTimeout(timer);
      enviou = response.ok;
    } catch (error) {
      enviou = false;
    }
    if (!enviou) guardarSugestaoLocal(payload);
    closeFeedback();
    toast(enviou
      ? "Sugestão registrada! O time técnico já foi notificado."
      : "Sugestão registrada neste navegador. O arquivo da sugestão foi baixado para o time técnico.");
  }

  function releaseCard(nota) {
    const versao = String(nota.versao || "");
    const atual = versao.startsWith("1.4");
    const itens = Array.isArray(nota.itens) ? nota.itens : [];
    return `<article class="release-card${atual ? " is-current" : ""}"><h3>v${escapeHtml(versao)} · ${escapeHtml(nota.data || "")}</h3><p class="release-meta">Solicitado por ${escapeHtml(nota.solicitante || "Natália")}</p><ul>${itens.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul></article>`;
  }

  async function openChangelog() {
    const lista = document.getElementById("changelog-list");
    lista.innerHTML = "<p class=\"release-meta\">Carregando o histórico…</p>";
    abrirModal(document.getElementById("modal-changelog"));
    let notas = NOVIDADES_FALLBACK;
    try {
      const response = await fetch("novidades.json", { cache: "no-store" });
      if (response.ok) {
        const dados = await response.json();
        if (Array.isArray(dados) && dados.length) notas = dados;
      }
    } catch (error) {
      notas = NOVIDADES_FALLBACK;
    }
    lista.innerHTML = notas.map(releaseCard).join("");
  }

  function closeChangelog() {
    fecharModal(document.getElementById("modal-changelog"));
  }

  const registerForm = document.getElementById("form-register");
  registerForm.addEventListener("input", (event) => {
    if (event.target && (event.target.name === "senha" || event.target.name === "confirmar")) {
      refreshPasswordFeedback();
    }
  });

  const productSearch = document.getElementById("product-search-input");
  if (productSearch) {
    productSearch.addEventListener("input", (event) => {
      state.productQuery = event.target.value || "";
      renderProducts();
    });
  }
  ["bi-inicio", "bi-fim"].forEach((id) => {
    const campo = document.getElementById(id);
    if (!campo) return;
    campo.addEventListener("change", () => {
      state.biPeriodo = "custom";
      renderPainelBi();
    });
  });

  const searchInput = document.getElementById("quick-search-input");
  searchInput.addEventListener("input", scheduleSearch);
  searchInput.addEventListener("keydown", onSearchKey);
  document.addEventListener("keydown", onEscapeSearch, true);
  document.addEventListener("keydown", onGlobalKey);
  document.addEventListener("click", onClick);
  MODAIS.forEach((id) => {
    const dialog = document.getElementById(id);
    if (!dialog) return;
    dialog.addEventListener("close", () => {
      dialog.classList.remove("ativo", "open");
      dialog.hidden = true;
    });
  });
  document.addEventListener("submit", onSubmit);
  document.addEventListener("dragstart", onFunilDragStart);
  document.addEventListener("dragover", onFunilDragOver);
  document.addEventListener("drop", onFunilDrop);
  document.addEventListener("change", onPerdaCategoria);
  renderDashboard();
  renderClientList();

  const restored = auth.readSession();
  if (restored) {
    enterApp(restored);
  } else {
    setAuthTab("login");
    showScreen("auth");
  }
})();
window.alternarEdicaoCliente = function () {
  const viewMode = document.getElementById("drawer-view-mode");
  const editMode = document.getElementById("drawer-edit-mode");
  const btnToggle = document.getElementById("btn-toggle-edit");
  const isEditing = editMode.style.display !== "none";

  if (isEditing) {
    editMode.style.display = "none";
    viewMode.style.display = "grid";
    btnToggle.style.display = "inline-block";
  } else {
    editMode.style.display = "block";
    viewMode.style.display = "none";
    btnToggle.style.display = "none";
  }
};

window.salvarEdicaoCliente = async function (event) {
  event.preventDefault();
  const client = getClient(state.drawerId);
  if (!client) return;

  const nomusId = client.nomusId || (typeof client.id === "string" ? client.id.replace("nomus-", "") : client.id);
  const btnSalvar = document.getElementById("btn-save-nomus-action");
  const feedback = document.getElementById("edit-feedback-msg");

  const payload = {
    telefone: document.getElementById("edit-nomus-telefone").value.trim(),
    email: document.getElementById("edit-nomus-email").value.trim(),
    observacoes: document.getElementById("edit-nomus-obs").value.trim()
  };

  btnSalvar.disabled = true;
  btnSalvar.textContent = "Sincronizando no ERP...";
  feedback.style.display = "none";

  try {
    const resposta = await fetch(`/api/clientes/${nomusId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json; charset=utf-8" },
      body: JSON.stringify(payload)
    });

    const resultado = await resposta.json();
    if (!resposta.ok || !resultado.sucesso) {
      throw new Error(resultado.erro || "Falha ao gravar no ERP");
    }

    client.telefone = payload.telefone;
    client.email = payload.email;
    client.anotacoes = payload.observacoes;

    feedback.textContent = "✓ Dados atualizados com sucesso no Nomus ERP!";
    feedback.style.color = "#4ade80";
    feedback.style.display = "block";

    setTimeout(() => {
      openClient(client.id);
    }, 1000);

  } catch (err) {
    feedback.textContent = `Erro: ${err.message}`;
    feedback.style.color = "#f87171";
    feedback.style.display = "block";
  } finally {
    btnSalvar.disabled = false;
    btnSalvar.textContent = "Salvar no Nomus";
  }
};