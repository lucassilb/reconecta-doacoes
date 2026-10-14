/* ReConecta — página do alimento doado (/excedentes/<id>), rodada 16.
   Dados à esquerda, ação à direita. Quem publicou vê "Sua doação", o estado e as ações
   (confirmar retirada, cancelar); a ONG reserva; os outros veem uma explicação curta e
   "Doar também". O servidor é a fonte da verdade: toda ação recarrega o estado dele. */
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
  function local(mu) { if (!mu) return ""; var p = String(mu).split("/"); return nome(p[0]) + (p[1] ? "/" + p[1].toUpperCase() : ""); }
  var numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  var PLURAL = { unidade: "unidades", pacote: "pacotes", caixa: "caixas" };
  function qtd(n, u) { return numero.format(Number(n) || 0) + " " + (PLURAL[u] && Number(n) !== 1 ? PLURAL[u] : (u || "")); }
  function dataHora(iso) {
    var d = R.dataBrasilia(iso);
    if (!d) return "";
    var hora = d.toLocaleTimeString("pt-BR", { timeZone: R.fuso, hour: "2-digit", minute: "2-digit" });
    var dia = R.diaISO(d) === R.diaISO(new Date()) ? "hoje"
      : d.toLocaleDateString("pt-BR", { timeZone: R.fuso, weekday: "short", day: "2-digit", month: "2-digit" });
    return dia + ", " + hora;
  }
  function validade(iso) {
    if (!iso) return "";
    if (iso === R.diaISO(new Date())) return "vence hoje";
    return iso.split("-").reverse().join("/");
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
  /* mesma foto da categoria que a Home usa (fotos reais quando a frente de fotos chegar) */
  var FOTOS_REAIS = true;
  var CAT = { "Hortifrúti": ["hortifruti", "hortifruti"], "Padaria": ["padaria", "padaria"], "Laticínios": ["laticinios", "laticinios"],
    "Carnes e peixes": ["carnes-peixes", "carnes"], "Grãos e cereais": ["graos-cereais", "graos"],
    "Refeições prontas": ["refeicoes-prontas", "refeicoes"], "Bebidas não alcoólicas": ["bebidas", "bebidas"], "Outros": ["outros", "outros"] };
  function pintarFoto(img, categoria) {
    var c = CAT[categoria] || CAT.Outros;
    var antiga = "/static/img/doacoes/cat-" + c[1] + ".webp";
    if (FOTOS_REAIS) {
      img.onerror = function () { img.onerror = null; img.src = antiga; };
      img.src = "/static/img/categorias/" + c[0] + ".webp";
    } else img.src = antiga;
  }

  /* estado em palavras */
  function estado(x) {
    if (x.status === "DISPONIVEL") return ["Aguardando uma ONG retirar", "exc-estado--espera"];
    if (x.status === "RESERVADO") return [x.reservado_por && x.reservado_por.nome ? "Reservado por " + nome(x.reservado_por.nome) : "Reservado por uma ONG", "exc-estado--reservado"];
    if (x.status === "RETIRADO") return ["Retirado", "exc-estado--ok"];
    if (x.status === "CANCELADO") return ["Cancelado", ""];
    if (x.status === "EXPIRADO") return ["Prazo de retirada encerrado", ""];
    return [x.status, ""];
  }

  var m = location.pathname.match(/\/excedentes\/(\d+)/);
  var ID = m ? m[1] : null;
  var excedente = null;
  var usuario;                 // undefined até a sessão responder

  /* ---------- os dados ---------- */

  function preencher(x) {
    var mudou = excedente && excedente.status !== x.status;
    excedente = x;
    var itens = x.itens || [];
    var i0 = itens[0] || {};
    var titulo = itens.length ? qtd(i0.quantidade, i0.unidade_medida) + " de " + i0.nome : "Alimento doado";
    document.title = (x.meu ? "Sua doação: " : "") + titulo + " · ReConecta";
    $("exc-titulo").textContent = titulo;
    $("exc-sua").hidden = x.meu !== true;
    pintarFoto($("exc-foto"), i0.categoria);
    var emp = x.empresa || {};
    $("exc-quem").replaceChildren("Doado por ", el("strong", { texto: emp.pessoa_fisica ? "Pessoa física" : nome(emp.nome) }),
      emp.municipio_uf ? " · " + local(emp.municipio_uf) : "", x.distancia ? " · " + x.distancia + " de você" : "");

    var s = estado(x);
    var sit = $("exc-situacao");
    if (sit.textContent !== s[0]) sit.textContent = s[0];      // só anuncia quando muda de verdade
    sit.className = "exc-estado " + s[1];
    $("exc-prazo").textContent = dataHora(x.retirar_ate);
    $("exc-falta").textContent = x.status === "DISPONIVEL" || x.status === "RESERVADO" ? falta(x.retirar_ate) : "";
    $("exc-validade").textContent = validade(i0.validade);
    var endereco = (x.retirada && x.retirada.endereco) || x.retirada_informada;
    $("exc-local").textContent = endereco || ((emp.municipio_uf ? local(emp.municipio_uf) + ". " : "") + "O endereço aparece para a ONG que reservar.");
    $("exc-obs-linha").hidden = !x.observacao;
    $("exc-obs").textContent = x.observacao || "";
    // com mais de um item, a lista completa; com um só, o título já diz tudo
    $("exc-itens").replaceChildren.apply($("exc-itens"), itens.length > 1 ? itens.map(function (i) {
      return el("li", null, [el("strong", { texto: i.nome }), el("span", { texto: qtd(i.quantidade, i.unidade_medida) + " · " + validade(i.validade) })]);
    }) : []);

    desenharAcao();
    $("exc-carregando").hidden = true;
    $("exc").hidden = false;
    return mudou;
  }

  function mostrarErroCarga(titulo, texto) {
    $("exc-carregando").hidden = true;
    var e = $("exc-erro");
    e.replaceChildren(el("p", { classe: "aviso__titulo", texto: titulo }), el("p", { texto: texto }),
      el("a", { classe: "btn btn--secundario btn--pequeno", href: "/#excedentes" }, ["Ver alimentos doados"]));
    e.hidden = false;
  }

  function carregar(aoVivo) {
    if (!ID) { mostrarErroCarga("Doação não encontrada", "O endereço desta página está incompleto."); return Promise.resolve(); }
    return requisitar("/reconecta/excedentes/" + ID).then(function (r) {
      if (r.status === 404) { if (!aoVivo) mostrarErroCarga("Doação não encontrada", "Ela pode ter sido removida."); return; }
      if (!r.ok) throw new Error("HTTP " + r.status);
      preencher(r.corpo);
    }).catch(function () {
      if (!aoVivo) mostrarErroCarga("Não conseguimos carregar esta doação", "Verifique sua conexão e recarregue a página.");
    });
  }

  /* ---------- ação conforme quem está vendo ---------- */

  function aviso(titulo, texto) {
    var a = $("exc-aviso");
    if (!titulo) { a.hidden = true; a.replaceChildren(); return; }
    a.replaceChildren(el("p", { texto: titulo }), texto ? el("p", { texto: texto }) : null);
    a.hidden = false;
  }

  function botao(rotulo, classe, acao) {
    var b = el("button", { type: "button", classe: "btn " + classe, texto: rotulo });
    b.addEventListener("click", function () { acao(b); });
    return b;
  }
  function link(rotulo, classe, href) { return el("a", { classe: "btn " + classe, href: href }, [rotulo]); }
  function texto(t, forte) { return el("p", { classe: forte ? "exc-acao__forte" : null, texto: t }); }

  /* Pergunta "tem certeza?" no próprio cartão, sem janela. */
  function confirmarNoCartao(pergunta, rotuloSim, executar) {
    var alvo = $("exc-acao");
    var sim = botao(rotuloSim, "btn--perigo", function (b) { executar(b); });
    var nao = botao("Voltar", "btn--secundario", function () { desenharAcao(); $("acao-titulo").focus(); });
    alvo.replaceChildren(texto(pergunta, true), sim, nao);
    sim.focus();
  }

  function agir(caminho, metodo, b, mensagens) {
    aviso("");
    if (R.tempoReal && R.tempoReal.silenciar) R.tempoReal.silenciar();
    b.disabled = true; b.classList.add("is-carregando");
    requisitar("/reconecta/excedentes/" + ID + caminho, metodo || "POST").then(function (r) {
      var c = r.corpo;
      if (r.ok) {
        // DELETE (cancelar a doação) responde 204 sem corpo: busca o estado novo
        if (r.status === 204 || !c.id) carregar(true).then(function () { $("acao-titulo").focus(); });
        else { preencher(c); $("acao-titulo").focus(); }
        return;
      }
      if (r.status === 401) { location.href = "/entrar?proximo=" + encodeURIComponent("/excedentes/" + ID); return; }
      aviso("Não foi possível concluir", mensagens[c.codigo] || c.mensagem || "Tente novamente em alguns instantes.");
      // 409: o estado mudou enquanto a pessoa decidia; mostra o estado novo
      if (r.status === 409 || r.status === 404) return carregar(true);
      b.disabled = false; b.classList.remove("is-carregando");
    }).catch(function () {
      aviso("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.");
      b.disabled = false; b.classList.remove("is-carregando");
    });
  }

  var MSG = {
    EXCEDENTE_INDISPONIVEL: "Esta doação acabou de ser reservada por outra ONG ou saiu do prazo.",
    APENAS_ONGS: "Só organizações sem fins lucrativos reservam.",
    EXCEDENTE_PROPRIO: "A doação é sua; quem reserva é uma ONG.",
    MUITAS_TENTATIVAS: "Muitas reservas em pouco tempo. Aguarde um pouco e tente de novo.",
    RESERVA_INDISPONIVEL: "Esta reserva já não pode ser cancelada.",
    RETIRADA_INDISPONIVEL: "Não há reserva dentro do prazo para confirmar."
  };

  function ehOng() { return !!(usuario && usuario.tipo === "empresa" && (usuario.perfis || []).indexOf("ong") !== -1); }
  function podeDoar() { return !!(usuario && (usuario.tipo === "doador" || (usuario.perfis || []).indexOf("empresa_alimentos") !== -1)); }
  function doarTambem() {
    return podeDoar() ? link("Doar também", "btn--secundario", "/painel#publicar-excedente")
                      : link("Doar também", "btn--secundario", "/?assistente=1");
  }

  function desenharAcao() {
    var alvo = $("exc-acao");
    var x = excedente;
    if (!x || usuario === undefined) return;
    var titulo = $("acao-titulo");
    var b = [];

    if (x.meu === true) {
      // quem doou: "Sua doação", o estado e as ações dela
      titulo.textContent = "Sua doação";
      if (x.status === "DISPONIVEL") {
        b.push(texto("Aguardando uma ONG reservar. Você é avisado no sino quando isso acontecer."),
          botao("Cancelar esta doação", "btn--perigo", function () {
            confirmarNoCartao("Cancelar a doação? Ela deixa de aparecer para as ONGs.", "Sim, cancelar a doação",
              function (bt) { agir("", "DELETE", bt, MSG); });
          }));
      } else if (x.status === "RESERVADO") {
        b.push(el("div", { classe: "exc-reserva" }, [
            el("p", { classe: "exc-reserva__rotulo", texto: "Reservado por" }),
            el("p", { classe: "exc-reserva__valor", texto: x.reservado_por ? nome(x.reservado_por.nome) : "uma ONG" }),
            el("p", { texto: "Retirada até " + dataHora(x.retirar_ate) + "." })]),
          texto("Quando a ONG buscar, confirme aqui."),
          botao("Confirmar retirada", "btn--primario", function (bt) { agir("/confirmar-retirada", "POST", bt, MSG); }),
          botao("Cancelar a reserva", "btn--perigo", function () {
            confirmarNoCartao("Cancelar a reserva desta ONG? A doação volta a ficar disponível.", "Sim, cancelar a reserva",
              function (bt) { agir("/cancelar-reserva", "POST", bt, MSG); });
          }));
      } else if (x.status === "RETIRADO") {
        b.push(texto("A ONG retirou. Obrigado por doar!", true), link("Doar de novo", "btn--primario", "/painel#publicar-excedente"));
      } else {
        b.push(texto(x.status === "EXPIRADO" ? "O prazo terminou sem retirada." : "Você cancelou esta doação."),
          link("Doar de novo", "btn--secundario", "/painel#publicar-excedente"));
      }
      b.push(link("Minhas doações no painel", "btn--secundario", "/painel"));
    } else if (x.retirada && x.status === "RESERVADO") {
      // a ONG que reservou
      titulo.textContent = "Reservado para a sua ONG";
      b.push(el("div", { classe: "exc-reserva" }, [
          el("p", { classe: "exc-reserva__rotulo", texto: "Retire neste endereço" }),
          el("p", { classe: "exc-reserva__valor", texto: x.retirada.endereco }),
          el("p", { texto: "Até " + dataHora(x.retirada.retirar_ate) + "." })]),
        botao("Cancelar reserva", "btn--secundario", function () {
          confirmarNoCartao("Cancelar a reserva? A doação volta a ficar disponível para outras ONGs.", "Sim, cancelar a reserva",
            function (bt) { agir("/cancelar-reserva", "POST", bt, MSG); });
        }),
        link("Minhas reservas no painel", "btn--secundario", "/painel"));
    } else if (x.retirada && x.status === "RETIRADO") {
      titulo.textContent = "Retirada confirmada";
      b.push(texto("A sua ONG retirou esta doação. Alimento aproveitado!"), link("Ver outros alimentos doados", "btn--secundario", "/#excedentes"));
    } else if (x.status !== "DISPONIVEL") {
      titulo.textContent = "Indisponível";
      b.push(texto({ RESERVADO: "Uma ONG já reservou. Se a reserva for cancelada, volta a aparecer.", RETIRADO: "Esta doação já foi retirada.",
        CANCELADO: "Quem doou cancelou.", EXPIRADO: "O prazo de retirada terminou." }[x.status] || "Esta doação não está disponível."),
        link("Ver outros alimentos doados", "btn--secundario", "/#excedentes"));
    } else if (!usuario) {
      titulo.textContent = "Para ONGs retirarem";
      b.push(texto("Uma ONG cadastrada reserva e retira no prazo."),
        link("Entrar como ONG para reservar", "btn--primario", "/entrar?proximo=" + encodeURIComponent("/excedentes/" + ID)),
        doarTambem());
    } else if (x.pode_reservar) {
      titulo.textContent = "Reservar";
      b.push(texto("Ao reservar, sua ONG se compromete a retirar no prazo. O endereço aparece logo depois."),
        botao("Reservar esta doação", "btn--primario", function (bt) { agir("/reservar", "POST", bt, MSG); }));
    } else if (x.motivo_bloqueio === "Apenas ONGs podem reservar" || !ehOng()) {
      // quem não é ONG não reserva, mas pode doar também
      titulo.textContent = "Para ONGs retirarem";
      b.push(texto("Esta doação é para uma ONG reservar e retirar."), doarTambem(),
        link("Ver pedidos das ONGs", "btn--secundario", "/#doacoes"));
    } else {
      titulo.textContent = "Reservar";
      b.push(texto((x.motivo_bloqueio || "Você não pode reservar esta doação") + "."),
        link("Ver outros alimentos doados", "btn--secundario", "/#excedentes"));
    }
    alvo.replaceChildren.apply(alvo, b);
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
