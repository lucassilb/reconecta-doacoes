/* ReConecta — página de um excedente (/excedentes/<id>): itens, prazo e estado ao vivo.
   ONG reserva e cancela a reserva; quem publicou vê quem reservou e confirma a retirada.
   O servidor é a fonte da verdade: toda ação recarrega o estado que ele devolve. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v == null || v === false) return;
      if (k === "texto") no.textContent = v;
      else if (k === "classe") no.className = v;
      else no.setAttribute(k, v === true ? "" : v);
    });
    (filhos || []).forEach(function (f) {
      if (f == null || f === "" || f === false) return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  function requisitar(url, metodo) {
    return fetch(url, { method: metodo || "GET", credentials: "same-origin", headers: { "Accept": "application/json" } })
      .then(function (r) {
        return r.text().then(function (t) {
          var c = null;
          try { c = t ? JSON.parse(t) : null; } catch (e) { c = null; }
          return { status: r.status, ok: r.ok, corpo: c == null ? {} : c };
        });
      });
  }

  /* ---------- formatação ---------- */

  var R = window.ReConecta;
  function nome(n) { return R.nomeTitulo(n); }
  function local(mu) { if (!mu) return ""; var p = String(mu).split("/"); return nome(p[0]) + (p[1] ? " / " + p[1].toUpperCase() : ""); }
  var numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  var PLURAL = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function qtd(n, u) { return numero.format(Number(n) || 0) + " " + (PLURAL[u] && Number(n) !== 1 ? PLURAL[u] : (u || "")); }
  function listaNomes(itens) {
    var nomes = itens.map(function (i) { return i.nome; });
    if (nomes.length <= 1) return nomes.join("");
    return nomes.slice(0, -1).join(", ") + " e " + nomes[nomes.length - 1];
  }
  function dataHora(iso) {
    var d = R.dataBrasilia(iso);
    if (!d) return "";
    var hora = d.toLocaleTimeString("pt-BR", { timeZone: R.fuso, hour: "2-digit", minute: "2-digit" });
    var dia = R.diaISO(d) === R.diaISO(new Date()) ? "hoje"
      : d.toLocaleDateString("pt-BR", { timeZone: R.fuso, weekday: "long", day: "2-digit", month: "long" });
    return dia + ", às " + hora;
  }
  function validade(iso) {
    var d = R.dataBrasilia(iso);
    if (!d) return "";
    if (iso === R.diaISO(new Date())) return "Vence hoje";
    return "Validade: " + d.toLocaleDateString("pt-BR", { timeZone: R.fuso, day: "2-digit", month: "2-digit", year: "numeric" });
  }
  function falta(iso) {
    var d = R.dataBrasilia(iso);
    if (!d) return "";
    var min = Math.floor((d.getTime() - Date.now()) / 60000);
    if (min < 1) return "";
    if (min < 60) return "(faltam " + min + " min)";
    var h = Math.floor(min / 60), resto = min % 60;
    if (h < 24) return "(faltam " + h + " h" + (resto ? " " + resto + " min" : "") + ")";
    var dias = Math.floor(h / 24);
    return "(faltam " + dias + (dias === 1 ? " dia" : " dias") + ")";
  }
  var IMG = { "Hortifrúti": "hortifruti", "Padaria": "padaria", "Laticínios": "laticinios", "Carnes e peixes": "carnes",
    "Grãos e cereais": "graos", "Refeições prontas": "refeicoes", "Bebidas não alcoólicas": "bebidas", "Outros": "outros" };

  var SITUACAO = {
    DISPONIVEL: ["Disponível", "selo"],
    RESERVADO: ["Reservado", "selo selo--acento"],
    RETIRADO: ["Retirado", "selo selo--cinza"],
    CANCELADO: ["Cancelado", "selo selo--cinza"],
    EXPIRADO: ["Prazo encerrado", "selo selo--cinza"]
  };

  var m = location.pathname.match(/\/excedentes\/(\d+)/);
  var ID = m ? m[1] : null;
  var excedente = null;
  var usuario;                 // undefined até a sessão responder

  /* ---------- o excedente ---------- */

  function itemLinha(i) {
    return el("li", { classe: "pedido-item" }, [
      el("img", { classe: "pedido-item__img", src: "/static/img/doacoes/cat-" + (IMG[i.categoria] || "outros") + ".webp", alt: "", width: "40", height: "40" }),
      el("div", { classe: "pedido-item__texto" }, [
        el("p", { classe: "pedido-item__linha" }, [el("strong", { texto: i.nome }), el("span", { texto: qtd(i.quantidade, i.unidade_medida) })]),
        el("p", { classe: "pedido-item__falta", texto: i.categoria + " · " + validade(i.validade) })
      ])
    ]);
  }

  function preencher(x) {
    var mudou = excedente && excedente.status !== x.status;
    excedente = x;
    var itens = x.itens || [];
    var titulo = itens.length ? "Excedente de " + listaNomes(itens).toLowerCase() : "Excedente de alimentos";
    document.title = titulo + " · ReConecta";
    $("exc-titulo").textContent = titulo;
    var emp = x.empresa || {};
    $("exc-empresa").replaceChildren(el("span", { classe: "det__empresa-icone", "aria-hidden": "true" }), el("span", null, [
      "Publicado por ", el("strong", { texto: nome(emp.nome) }), emp.municipio_uf ? " · " + local(emp.municipio_uf) : ""]));
    $("exc-empresa").firstChild.innerHTML = '<svg viewBox="0 0 24 24" focusable="false"><path d="M4 9.5 5.6 5A1.6 1.6 0 0 1 7.1 4h9.8a1.6 1.6 0 0 1 1.5 1L20 9.5M4 9.5h16v1a2.7 2.7 0 0 1-5.3 0 2.7 2.7 0 0 1-5.4 0A2.7 2.7 0 0 1 4 10.5zM5.5 13.500V20h13v-6.500M10 20v-4h4v4" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg>';

    var s = SITUACAO[x.status] || [x.status, "selo selo--cinza"];
    var sit = $("exc-situacao");
    if (sit.textContent !== s[0]) sit.textContent = s[0];      // só anuncia quando muda de verdade
    sit.className = s[1];
    $("exc-prazo").textContent = dataHora(x.retirar_ate);
    $("exc-falta").textContent = x.status === "DISPONIVEL" || x.status === "RESERVADO" ? falta(x.retirar_ate) : "";
    $("exc-local").textContent = x.retirada && x.retirada.endereco
      ? x.retirada.endereco
      : (emp.municipio_uf ? local(emp.municipio_uf) + ". " : "") + "O endereço completo aparece para a ONG que reservar.";
    $("exc-obs-linha").hidden = !x.observacao;
    $("exc-obs").textContent = x.observacao || "";
    $("exc-itens").replaceChildren.apply($("exc-itens"), itens.map(itemLinha));

    desenharAcao();
    $("exc-carregando").hidden = true;
    $("exc").hidden = false;
    return mudou;
  }

  function mostrarErroCarga(titulo, texto) {
    $("exc-carregando").hidden = true;
    var e = $("exc-erro");
    e.replaceChildren(el("p", { classe: "aviso__titulo", texto: titulo }), el("p", { texto: texto }),
      el("a", { classe: "btn btn--secundario btn--pequeno", href: "/#excedentes" }, ["Ver excedentes de hoje"]));
    e.hidden = false;
  }

  function carregar(aoVivo) {
    if (!ID) { mostrarErroCarga("Excedente não encontrado", "O endereço desta página está incompleto."); return Promise.resolve(); }
    return requisitar("/reconecta/excedentes/" + ID).then(function (r) {
      if (r.status === 404) { if (!aoVivo) mostrarErroCarga("Excedente não encontrado", "Ele pode ter sido removido."); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      preencher(r.corpo);
    }).catch(function () {
      if (!aoVivo) mostrarErroCarga("Não conseguimos carregar este excedente", "Verifique sua conexão e recarregue a página.");
    });
  }

  /* ---------- ação conforme quem está vendo ---------- */

  function aviso(titulo, texto) {
    var a = $("exc-aviso");
    if (!titulo) { a.hidden = true; a.replaceChildren(); return; }
    a.replaceChildren(el("p", { classe: "quest__aviso-titulo", texto: titulo }), texto ? el("p", { texto: texto }) : null);
    a.hidden = false;
  }

  function botao(rotulo, classe, acao) {
    var b = el("button", { type: "button", classe: "btn " + classe + " btn--largo", texto: rotulo });
    b.addEventListener("click", function () { acao(b); });
    return b;
  }

  /* Pergunta "tem certeza?" no próprio cartão, sem janela. */
  function confirmarNoCartao(pergunta, rotuloSim, executar) {
    var alvo = $("exc-acao");
    var sim = botao(rotuloSim, "btn--perigo", function (b) { executar(b); });
    var nao = botao("Voltar", "btn--fantasma", function () { desenharAcao(); $("acao-titulo").focus(); });
    alvo.replaceChildren(el("p", { classe: "exc__pergunta", texto: pergunta }), sim, nao);
    sim.focus();
  }

  function agir(caminho, metodo, b, mensagens) {
    aviso("");
    if (R.tempoReal && R.tempoReal.silenciar) R.tempoReal.silenciar();
    b.disabled = true; b.classList.add("is-carregando");
    requisitar("/reconecta/excedentes/" + ID + caminho, metodo || "POST").then(function (r) {
      var c = r.corpo;
      if (r.ok) { preencher(c); $("acao-titulo").focus(); return; }
      if (r.status === 401) { location.href = "/entrar?proximo=" + encodeURIComponent("/excedentes/" + ID); return; }
      var texto = mensagens[c.codigo] || c.mensagem || "Tente novamente em alguns instantes.";
      aviso("Não foi possível concluir", texto);
      // 409: o estado mudou enquanto a pessoa decidia; mostra o estado novo
      if (r.status === 409 || r.status === 404) return carregar(true);
      b.disabled = false; b.classList.remove("is-carregando");
    }).catch(function () {
      aviso("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.");
      b.disabled = false; b.classList.remove("is-carregando");
    });
  }

  var MSG = {
    EXCEDENTE_INDISPONIVEL: "Este excedente acabou de ser reservado por outra ONG ou saiu do prazo.",
    APENAS_ONGS: "Só organizações sem fins lucrativos reservam excedentes.",
    EXCEDENTE_PROPRIO: "Você publicou este excedente; quem reserva é uma ONG.",
    MUITAS_TENTATIVAS: "Muitas reservas em pouco tempo. Aguarde um pouco e tente de novo.",
    RESERVA_INDISPONIVEL: "Esta reserva já não pode ser cancelada.",
    RETIRADA_INDISPONIVEL: "Não há reserva dentro do prazo para confirmar."
  };

  function desenharAcao() {
    var alvo = $("exc-acao");
    var x = excedente;
    if (!x || usuario === undefined) return;
    var titulo = $("acao-titulo");
    var eu = usuario && usuario.tipo === "empresa" ? usuario : null;
    // o detalhe não traz o id de quem publicou: reconhece pelo nome da própria organização
    // (e por reservado_por, que o servidor só manda para o publicador)
    var souPublicador = !!(eu && (x.reservado_por || (x.empresa && x.empresa.nome === eu.nome)));
    var reserveiEu = !!x.retirada;
    var blocos = [];

    if (reserveiEu && x.status === "RESERVADO") {
      titulo.textContent = "Reservado para a sua ONG";
      blocos.push(
        el("div", { classe: "exc__reserva" }, [
          el("p", { classe: "exc__reserva-titulo", texto: "Retire neste endereço" }),
          el("p", { classe: "exc__endereco", texto: x.retirada.endereco }),
          el("p", null, ["Até ", el("strong", { texto: dataHora(x.retirada.retirar_ate) }), "."])
        ]),
        el("p", { classe: "doar__texto", texto: "Na retirada, a empresa confirma a entrega pelo site. Se não puder ir, cancele para outra ONG aproveitar." }),
        botao("Cancelar reserva", "btn--secundario", function () {
          confirmarNoCartao("Cancelar a reserva? O excedente volta a ficar disponível para outras ONGs.", "Sim, cancelar a reserva",
            function (b) { agir("/cancelar-reserva", "POST", b, MSG); });
        }),
        el("a", { classe: "btn btn--fantasma btn--largo", href: "/painel" }, ["Ver minhas reservas no painel"])
      );
    } else if (reserveiEu && x.status === "RETIRADO") {
      titulo.textContent = "Retirada confirmada";
      blocos.push(el("p", { classe: "doar__texto", texto: "A empresa confirmou que a sua ONG retirou este excedente. Alimento aproveitado!" }),
        el("a", { classe: "btn btn--secundario btn--largo", href: "/#excedentes" }, ["Ver outros excedentes"]));
    } else if (souPublicador) {
      titulo.textContent = "Seu excedente";
      if (x.status === "RESERVADO" && x.reservado_por) {
        blocos.push(
          el("div", { classe: "exc__reserva" }, [
            el("p", { classe: "exc__reserva-titulo", texto: "Reservado por" }),
            el("p", { classe: "exc__endereco", texto: nome(x.reservado_por.nome) }),
            el("p", null, ["Retirada até ", el("strong", { texto: dataHora(x.retirar_ate) }), "."])
          ]),
          botao("Confirmar retirada", "btn--primario", function (b) { agir("/confirmar-retirada", "POST", b, MSG); }),
          botao("Cancelar a reserva", "btn--fantasma", function () {
            confirmarNoCartao("Cancelar a reserva desta ONG? O excedente volta a ficar disponível.", "Sim, cancelar a reserva",
              function (b) { agir("/cancelar-reserva", "POST", b, MSG); });
          })
        );
      } else if (x.status === "DISPONIVEL") {
        blocos.push(el("p", { classe: "doar__texto", texto: "Aguardando a reserva de uma ONG. Você é avisado na hora, aqui e no sino de notificações." }));
      } else if (x.status === "RETIRADO") {
        blocos.push(el("p", { classe: "doar__texto", texto: "Você confirmou a retirada. Alimento aproveitado!" }));
      } else {
        blocos.push(el("p", { classe: "doar__bloqueio", texto: x.status === "EXPIRADO" ? "O prazo de retirada terminou sem retirada confirmada." : "Este excedente foi cancelado." }));
      }
      blocos.push(el("a", { classe: "btn btn--fantasma btn--largo", href: "/painel" }, ["Gerenciar no painel"]));
    } else if (x.status !== "DISPONIVEL") {
      titulo.textContent = "Excedente indisponível";
      var motivo = { RESERVADO: "Uma ONG já reservou este excedente. Se a reserva for cancelada, ele volta a aparecer aqui na hora.",
        RETIRADO: "Este excedente já foi retirado por uma ONG.", CANCELADO: "A empresa cancelou este excedente.",
        EXPIRADO: "O prazo de retirada deste excedente terminou." }[x.status] || "Este excedente não está disponível.";
      blocos.push(el("p", { classe: "doar__bloqueio", texto: motivo }),
        el("a", { classe: "btn btn--secundario btn--largo", href: "/#excedentes" }, ["Ver outros excedentes"]));
    } else if (!usuario) {
      titulo.textContent = "Reservar este excedente";
      blocos.push(el("p", { classe: "doar__texto", texto: "A reserva é feita por ONGs cadastradas. Depois de reservar, o endereço de retirada aparece aqui." }),
        el("a", { classe: "btn btn--primario btn--largo", href: "/entrar?proximo=" + encodeURIComponent("/excedentes/" + ID) }, ["Entre como ONG para reservar"]),
        el("p", { classe: "doar__nota" }, ["Sua organização ainda não tem conta? ", el("a", { href: "/cadastro", texto: "Cadastre a ONG com o CNPJ" }), "."]));
    } else if (x.pode_reservar) {
      titulo.textContent = "Reservar este excedente";
      blocos.push(el("p", { classe: "doar__texto", texto: "Ao reservar, a sua ONG se compromete a retirar no prazo. O endereço aparece logo depois." }),
        botao("Reservar este excedente", "btn--primario", function (b) { agir("/reservar", "POST", b, MSG); }));
    } else {
      titulo.textContent = "Reservar este excedente";
      blocos.push(el("p", { classe: "doar__bloqueio", texto: (x.motivo_bloqueio || "Você não pode reservar este excedente") + "." }),
        el("p", { classe: "doar__nota", texto: "Excedentes são reservados por organizações sem fins lucrativos. Quem tem alimento pode doar para os pedidos abertos." }),
        el("a", { classe: "btn btn--secundario btn--largo", href: "/#doacoes" }, ["Ver pedidos abertos"]));
    }
    alvo.replaceChildren.apply(alvo, blocos);
  }

  /* ---------- sessão, tempo real e relógio ---------- */

  document.addEventListener("reconecta:sessao", function (e) {
    var antes = usuario;
    usuario = (e.detail && e.detail.usuario) || null;
    // a resposta do servidor depende de quem pergunta: recarrega se a sessão mudou depois da carga
    if (antes !== undefined && excedente) carregar(true); else desenharAcao();
  });

  var relogio = null;
  document.addEventListener("reconecta:evento", function (e) {
    var d = e.detail || {};
    if (String(d.tipo || "").indexOf("excedente.") !== 0 || String((d.dados || {}).excedente_id) !== String(ID)) return;
    clearTimeout(relogio);
    relogio = setTimeout(function () { carregar(true); }, 200);
  });

  setInterval(function () {
    if (!excedente || (excedente.status !== "DISPONIVEL" && excedente.status !== "RESERVADO")) return;
    var d = R.dataBrasilia(excedente.retirar_ate);
    if (d && d.getTime() <= Date.now()) carregar(true);      // passou do prazo: o servidor diz o estado
    else $("exc-falta").textContent = falta(excedente.retirar_ate);
  }, 30000);

  carregar();
})();
