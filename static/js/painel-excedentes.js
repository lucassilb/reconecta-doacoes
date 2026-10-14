/* Excedentes do painel: o servidor decide permissões e estados. */
(function () {
  "use strict";
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "texto") no.textContent = attrs[k];
      else if (k === "classe") no.className = attrs[k];
      else no.setAttribute(k, attrs[k]);
    });
    (filhos || []).forEach(function (filho) {
      if (filho != null) no.appendChild(typeof filho === "string" ? document.createTextNode(filho) : filho);
    });
    return no;
  }
  function pedir(url, opcoes) {
    opcoes = opcoes || {};
    return fetch(url, {
      method: opcoes.method || "GET", credentials: "same-origin",
      headers: { "Accept": "application/json", "Content-Type": "application/json" },
      body: opcoes.body == null ? undefined : JSON.stringify(opcoes.body)
    }).then(function (r) {
      return r.text().then(function (texto) {
        var corpo = {};
        try { corpo = texto ? JSON.parse(texto) : {}; } catch (e) { /* 204 */ }
        return { ok: r.ok, status: r.status, corpo: corpo };
      });
    });
  }
  function hora(iso) {
    var d = window.ReConecta.dataBrasilia(iso);
    return d ? d.toLocaleString("pt-BR", { timeZone: window.ReConecta.fuso, dateStyle: "short", timeStyle: "short" }) : String(iso || "");
  }
  function aviso(texto, erro) {
    var alvo = $("ex-aviso");
    alvo.className = "aviso" + (erro ? " aviso--erro" : " aviso--ok");
    alvo.textContent = texto;
    alvo.hidden = false;
  }
  function campo(rotulo, input, id) {
    input.id = id;
    input.className = "campo__entrada";
    return el("div", { classe: "campo" }, [
      el("label", { for: id, classe: "campo__rotulo", texto: rotulo }), input
    ]);
  }
  var opcoes = { categorias: [], unidades: [] };
  var linhas = [];
  var sequencia = 0;
  function seletor(lista, rotulo) {
    var no = el("select");
    no.appendChild(el("option", { value: "", texto: rotulo }));
    lista.forEach(function (valor) { no.appendChild(el("option", { value: valor, texto: valor })); });
    return no;
  }
  function adicionarItem() {
    var id = "ex-item-" + (++sequencia);
    var nome = el("input", { type: "text", maxlength: "100", required: "" });
    var categoria = seletor(opcoes.categorias, "Selecione");
    var quantidade = el("input", { type: "number", min: "0.01", max: "99999999.99", step: "0.01", inputmode: "decimal", required: "" });
    var unidade = seletor(opcoes.unidades, "Selecione");
    var validade = el("input", { type: "date", min: window.ReConecta.diaISO(new Date()), required: "" });
    var registro = { nome: nome, categoria: categoria, quantidade: quantidade, unidade_medida: unidade, validade: validade };
    var remover = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: "Remover item", "aria-label": "Remover este item" });
    var linha = el("div", { classe: "item ex-item" }, [
      el("div", { classe: "ex-item__grade" }, [
        campo("Alimento", nome, id + "-nome"), campo("Categoria", categoria, id + "-categoria"),
        campo("Quantidade", quantidade, id + "-quantidade"), campo("Unidade", unidade, id + "-unidade"),
        campo("Validade", validade, id + "-validade")
      ]), remover
    ]);
    remover.addEventListener("click", function () {
      linhas = linhas.filter(function (item) { return item !== registro; });
      linha.remove();
    });
    linhas.push(registro);
    $("ex-itens").appendChild(linha);
    nome.focus();
  }
  function validar() {
    var erros = [];
    var prazo = $("ex-retirar-ate").value;
    var hoje = window.ReConecta.diaISO(new Date());
    var prazoReal = prazo && window.ReConecta.dataBrasilia(prazo);
    $("ex-retirar-ate-erro").textContent = "";
    $("ex-itens-erro").textContent = "";
    $("ex-declaracoes-erro").textContent = "";
    if (!prazoReal || prazoReal <= new Date()) {
      $("ex-retirar-ate-erro").textContent = "Informe uma data e hora futuras de Brasília.";
      erros.push($("ex-retirar-ate"));
    }
    if (!linhas.length) {
      $("ex-itens-erro").textContent = "Adicione pelo menos um item.";
      erros.push($("ex-add-item"));
    }
    linhas.forEach(function (item) {
      var q = Number(item.quantidade.value);
      if (!item.nome.value.trim() || !item.categoria.value || !item.unidade_medida.value ||
          !item.quantidade.value || q < 0.01 || q > 99999999.99 || Math.round(q * 100) / 100 !== q ||
          !item.validade.value || item.validade.value < hoje) {
        $("ex-itens-erro").textContent = "Preencha alimento, categoria, quantidade, unidade e validade de cada item.";
        erros.push(item.nome);
      }
      if (prazo && item.validade.value && prazo.slice(0, 10) > item.validade.value) {
        $("ex-retirar-ate-erro").textContent = "A retirada deve ocorrer até a primeira validade.";
        erros.push($("ex-retirar-ate"));
      }
    });
    var declaracoes = ["dentro-validade", "embalagem-ok", "armazenado-ok"].concat(pessoaFisica ? ["nao-caseiro"] : []);
    declaracoes.forEach(function (nome) {
      if (!$("ex-" + nome).checked) {
        $("ex-declaracoes-erro").textContent = pessoaFisica ? "Confirme as quatro condições para publicar." : "Confirme as três condições para publicar.";
        erros.push($("ex-" + nome));
      }
    });
    if (pessoaFisica) {
      $("ex-retirada-erro").textContent = "";
      var cep = $("ex-ret-cep").value.replace(/\D/g, "");
      if (!$("ex-ret-logradouro").value.trim() || !$("ex-ret-numero").value.trim() ||
          !$("ex-ret-municipio").value.trim() || !$("ex-ret-uf").value || (cep && cep.length !== 8)) {
        $("ex-retirada-erro").textContent = "Informe rua, número, cidade e UF (o CEP, se informar, com 8 números).";
        erros.push(!$("ex-ret-logradouro").value.trim() ? $("ex-ret-logradouro") : !$("ex-ret-numero").value.trim() ? $("ex-ret-numero")
          : !$("ex-ret-municipio").value.trim() ? $("ex-ret-municipio") : !$("ex-ret-uf").value ? $("ex-ret-uf") : $("ex-ret-cep"));
      }
    }
    if (erros.length) erros[0].focus();
    return !erros.length;
  }
  function publicar(evento) {
    evento.preventDefault();
    $("ex-aviso").hidden = true;
    if (!validar()) return;
    var btn = $("ex-publicar");
    btn.disabled = true;
    var corpo = {
      retirar_ate: $("ex-retirar-ate").value,
      observacao: $("ex-observacao").value.trim(),
      dentro_validade: true, embalagem_ok: true, armazenado_ok: true,
      itens: linhas.map(function (item) {
        return {
          nome: item.nome.value.trim(), categoria: item.categoria.value,
          quantidade: Number(item.quantidade.value), unidade_medida: item.unidade_medida.value,
          validade: item.validade.value
        };
      })
    };
    if (pessoaFisica) {
      corpo.nao_caseiro = true;
      corpo.retirada = {
        logradouro: $("ex-ret-logradouro").value.trim(), numero: $("ex-ret-numero").value.trim(),
        bairro: $("ex-ret-bairro").value.trim(), municipio: $("ex-ret-municipio").value.trim(),
        uf: $("ex-ret-uf").value, cep: $("ex-ret-cep").value.replace(/\D/g, "")
      };
    }
    pedir("/reconecta/excedentes", { method: "POST", body: corpo }).then(function (r) {
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      if (!r.ok) {
        var campos = r.corpo.campos || {};
        var deRetirada = Object.keys(campos).filter(function (k) { return k.indexOf("retirada.") === 0; });
        if (deRetirada.length) $("ex-retirada-erro").textContent = campos[deRetirada[0]];
        aviso(deRetirada.length ? campos[deRetirada[0]] : (r.corpo.mensagem || "Não foi possível publicar o excedente."), true);
        return;
      }
      aviso(pessoaFisica ? "Publicado. As ONGs perto de você são avisadas e, quando uma reservar, você recebe o aviso no sino."
                         : "Excedente publicado. ONGs já podem reservá-lo.", false);
      $("form-excedente").reset();
      linhas = [];
      $("ex-itens").replaceChildren();
      adicionarItem();
      carregarMeus();
    }).catch(function () { aviso("Sem conexão com o servidor. Tente novamente.", true); })
      .then(function () { btn.disabled = false; });
  }
  var STATUS = {
    DISPONIVEL: ["Disponível", ""], RESERVADO: ["Reservado", "selo--acento"],
    RETIRADO: ["Retirado", ""], CANCELADO: ["Cancelado", "selo--cinza"],
    EXPIRADO: ["Prazo expirado", "selo--cinza"]
  };
  function acao(rotulo, url, metodo, local, confirmar) {
    var btn = el("button", { type: "button", classe: "btn btn--secundario btn--pequeno", texto: rotulo });
    btn.addEventListener("click", function () {
      if (confirmar && btn.dataset.confirmar !== "sim") {
        btn.dataset.confirmar = "sim";
        btn.textContent = "Sim, " + rotulo.toLowerCase();
        return;
      }
      btn.disabled = true;
      pedir(url, { method: metodo }).then(function (r) {
        if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
        if (!r.ok) {
          local.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: r.corpo.mensagem || "A operação não foi concluída. Atualize a lista." }));
          return;
        }
        carregarMeus(); carregarReservas();
      }).catch(function () {
        local.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: "Sem conexão com o servidor. Tente atualizar." }));
      }).then(function () { btn.disabled = false; });
    });
    return btn;
  }
  function cartao(item, propria) {
    var estado = STATUS[item.status] || STATUS.DISPONIVEL;
    var nome = item.empresa && item.empresa.nome ? item.empresa.nome : "Organização";
    var cartao = el("article", { classe: "doacao ex-cartao" }, [
      el("div", { classe: "doacao__topo" }, [
        el("a", { href: "/excedentes/" + item.id, classe: "doacao__onde", texto: propria ? "Excedente #" + item.id : nome }),
        el("span", { classe: "selo " + estado[1], texto: estado[0] })
      ]),
      el("p", { classe: "doacao__prazo", texto: "Retirar até " + hora(item.retirar_ate) }),
      el("ul", { classe: "pedido-itens-painel" }, (item.itens || []).map(function (i) {
        return el("li", { classe: "pedido-linha", texto: i.nome + " · " + i.quantidade + " " + i.unidade_medida + " · validade " + i.validade.split("-").reverse().join("/") });
      }))
    ]);
    if (item.reservado_por) cartao.appendChild(el("p", { classe: "doacao__retirada", texto: "Reservado por " + item.reservado_por.nome }));
    if (!propria && item.retirada && item.retirada.endereco) cartao.appendChild(el("p", { classe: "doacao__retirada", texto: "Retirar em: " + item.retirada.endereco }));
    var acoes = el("div", { classe: "doacao__acoes", "aria-live": "polite" });
    var base = "/reconecta/excedentes/" + item.id;
    if (propria && item.status === "RESERVADO") {
      acoes.appendChild(acao("Confirmar retirada", base + "/confirmar-retirada", "POST", acoes, true));
      acoes.appendChild(acao("Cancelar reserva", base + "/cancelar-reserva", "POST", acoes, true));
    } else if (propria && item.status === "DISPONIVEL") {
      acoes.appendChild(acao("Cancelar excedente", base, "DELETE", acoes, true));
    } else if (!propria && item.status === "RESERVADO") {
      acoes.appendChild(acao("Cancelar reserva", base + "/cancelar-reserva", "POST", acoes, true));
    }
    if (acoes.childNodes.length) cartao.appendChild(acoes);
    return cartao;
  }
  function carregarLista(url, id, propria) {
    var lista = $(id);
    if (!lista || lista.closest("section").hidden) return;
    lista.setAttribute("aria-busy", "true");
    pedir(url).then(function (r) {
      if (!r.ok || !Array.isArray(r.corpo)) throw new Error("lista");
      lista.replaceChildren();
      if (!r.corpo.length) {
        lista.appendChild(el("p", { classe: "doacoes__vazio", texto: propria ? "Você ainda não publicou excedentes." : "Você ainda não reservou excedentes." }));
      } else r.corpo.forEach(function (item) { lista.appendChild(cartao(item, propria)); });
    }).catch(function () {
      lista.replaceChildren(el("p", { classe: "doacoes__vazio", texto: "Não foi possível carregar a lista. Tente atualizar." }));
    }).then(function () { lista.setAttribute("aria-busy", "false"); });
  }
  function carregarMeus() { carregarLista("/reconecta/excedentes/meus", "ex-lista-meus", true); }
  function carregarReservas() { carregarLista("/reconecta/excedentes/reservas", "ex-lista-reservas", false); }
  /* Rota de coleta da ONG: o servidor ordena as retiradas (vizinho mais próximo + 2-opt). */
  function km(valor) {
    return Number(valor).toLocaleString("pt-BR", { maximumFractionDigits: Number(valor) < 10 ? 1 : 0 }) + " km";
  }
  function linkMapa(href, texto, rotulo) {
    return el("a", { classe: "link-seta", href: href, target: "_blank", rel: "noopener noreferrer", "aria-label": rotulo, texto: texto });
  }
  function desenharRota(rota) {
    var alvo = $("ex-rota-resultado");
    var paradas = rota.paradas || [];
    var blocos = [];
    if (!paradas.length && !(rota.sem_localizacao || []).length) {
      blocos.push(el("p", { classe: "doacoes__vazio", texto: "Você não tem retiradas pendentes. Reserve excedentes para montar a rota." }));
    }
    if (paradas.length) {
      blocos.push(el("p", { classe: "doacao__retirada" }, [
        el("strong", { texto: paradas.length + (paradas.length === 1 ? " parada" : " paradas") + " · " + km(rota.total_km) }),
        " em linha reta, saindo de " + (rota.partida && rota.partida.nome ? rota.partida.nome : "sua organização") +
        " e voltando (" + km(rota.retorno_km) + " na volta). O mapa traça o caminho pelas ruas."]));
      blocos.push(el("ol", { classe: "doacoes rota-coleta", style: "margin:0;padding:0;list-style:none", "aria-label": "Ordem das retiradas" }, paradas.map(function (p) {
        return el("li", { classe: "doacao" }, [
          el("div", { classe: "doacao__topo" }, [
            el("a", { classe: "doacao__onde", href: "/excedentes/" + p.excedente_id, texto: p.ordem + "ª parada · " + p.empresa }),
            el("span", { classe: "selo", texto: km(p.distancia_km) + (p.ordem === 1 ? " da saída" : " da anterior") })
          ]),
          el("p", { classe: "doacao__retirada", texto: p.endereco }),
          el("p", { classe: "doacao__prazo", texto: "Retirar até " + hora(p.retirar_ate) + ((p.itens || []).length ? " · " + p.itens.join(", ") : "") }),
          el("div", { classe: "doacao__acoes" }, [linkMapa(p.link_osm, "Ver o trecho no mapa", "Ver no OpenStreetMap o trecho até " + p.empresa)])
        ]);
      })));
      blocos.push(el("div", { classe: "doacao__acoes" }, [linkMapa(rota.link_rota, "Abrir a rota completa no mapa", "Abrir a rota completa no mapa (OpenStreetMap)")]));
      if (rota.aproximada) blocos.push(el("p", { classe: "doacoes__vazio", texto: "Algum endereço foi localizado só pela cidade; a distância desse trecho é aproximada." }));
    }
    (rota.sem_localizacao || []).forEach(function (s) {
      blocos.push(el("p", { classe: "doacao__retirada", texto: "Sem localização no mapa, inclua por conta própria: " + s.empresa + " — " + s.endereco }));
    });
    alvo.replaceChildren.apply(alvo, blocos);
    alvo.hidden = false;
  }
  function carregarRota() {
    var btn = $("ex-rota"), alvo = $("ex-rota-resultado");
    btn.disabled = true;
    btn.setAttribute("aria-expanded", "true");
    alvo.setAttribute("aria-busy", "true");
    pedir("/reconecta/excedentes/rota").then(function (r) {
      if (r.status === 401) { location.replace("/entrar?proximo=/painel"); return; }
      if (!r.ok) throw new Error(r.corpo.mensagem || "rota");
      desenharRota(r.corpo);
      alvo.focus();
    }).catch(function (erro) {
      alvo.replaceChildren(el("p", { classe: "campo__erro", role: "alert", texto: erro && erro.message !== "rota" ? erro.message : "Não foi possível montar a rota agora. Tente de novo." }));
      alvo.hidden = false;
    }).then(function () { btn.disabled = false; alvo.setAttribute("aria-busy", "false"); });
  }
  $("ex-rota").addEventListener("click", carregarRota);
  $("ex-recarregar-meus").addEventListener("click", carregarMeus);
  $("ex-recarregar-reservas").addEventListener("click", carregarReservas);
  $("ex-add-item").addEventListener("click", adicionarItem);
  $("form-excedente").addEventListener("submit", publicar);
  var recargaPendente;
  document.addEventListener("reconecta:evento", function (evento) {
    if (evento.detail && /^excedente\./.test(evento.detail.tipo)) {
      clearTimeout(recargaPendente);
      recargaPendente = setTimeout(function () {
        carregarMeus(); carregarReservas();
        if (!$("ex-rota-resultado").hidden) carregarRota();  // rota aberta acompanha reservas e retiradas
      }, 200);
    }
  });
  /* Vindo do assistente da Home ("Publicar como excedente"): os itens já interpretados
     entram no formulário; validade, prazo e declarações continuam por conta da empresa. */
  function aplicarRascunho() {
    var bruto = null;
    try { bruto = sessionStorage.getItem("reconecta:rascunho-excedente"); sessionStorage.removeItem("reconecta:rascunho-excedente"); } catch (e) { return; }
    var rascunho = null;
    try { rascunho = bruto ? JSON.parse(bruto) : null; } catch (e) { return; }
    var itens = rascunho && Array.isArray(rascunho.itens) ? rascunho.itens.slice(0, 10) : [];
    if (!itens.length) return;
    $("ex-itens").replaceChildren();
    linhas = [];
    itens.forEach(function (item) {
      adicionarItem();
      var linha = linhas[linhas.length - 1];
      linha.nome.value = String(item.nome || "").slice(0, 100);
      if (opcoes.categorias.indexOf(item.categoria) !== -1) linha.categoria.value = item.categoria;
      if (Number(item.quantidade) > 0) linha.quantidade.value = String(Number(item.quantidade));
      if (opcoes.unidades.indexOf(item.unidade_medida) !== -1) linha.unidade_medida.value = item.unidade_medida;
    });
    aviso("Trouxemos do assistente " + (itens.length === 1 ? "o item" : "os " + itens.length + " itens") +
      ". Confira, informe a validade e o prazo de retirada e publique.", false);
    linhas[0].validade.focus();
  }

  var iniciou = false;
  var pessoaFisica = false;
  function iniciar(usuario) {
      if (iniciou) return;
      if (!usuario) return;
      var perfis = Array.isArray(usuario.perfis) ? usuario.perfis : [];
      // pessoa física também publica o que sobrou, informando onde a ONG retira
      pessoaFisica = usuario.tipo === "doador";
      var ong = !pessoaFisica && perfis.indexOf("ong") !== -1;
      var alimentos = pessoaFisica || perfis.indexOf("empresa_alimentos") !== -1;
      if (!ong && !alimentos) return;
      if (pessoaFisica) {
        $("publicar-excedente-t").textContent = "Doar o que sobrou";
        $("publicar-excedente-sub").textContent = "Sem pedido aberto para o seu alimento? Publique aqui: as ONGs perto de você são avisadas, uma reserva e retira no endereço que você informar.";
        $("meus-excedentes-t").textContent = "Meus alimentos publicados";
        $("ex-retirada").hidden = false;
        $("ex-nao-caseiro-linha").hidden = false;
        $("ex-publicar").textContent = "Publicar para as ONGs";
        $("ex-ret-cep").addEventListener("input", function () {
          var d = this.value.replace(/\D/g, "").slice(0, 8);
          this.value = d.length > 5 ? d.slice(0, 5) + "-" + d.slice(5) : d;
        });
      }
      iniciou = true;
      $("bloco-excedentes").hidden = false;
      if (alimentos) {
        $("publicar-excedente").hidden = false;
        $("meus-excedentes").hidden = false;
        pedir("/reconecta/publico/opcoes").then(function (r) {
          if (r.ok) opcoes = r.corpo;
          adicionarItem();
        }).catch(function () { adicionarItem(); }).then(aplicarRascunho);
        carregarMeus();
        // o bloco estava oculto na carga: o navegador não rola sozinho até a âncora
        if (location.hash === "#publicar-excedente") {
          $("publicar-excedente").scrollIntoView({ block: "start" });
          $("publicar-excedente-t").setAttribute("tabindex", "-1");
          $("publicar-excedente-t").focus({ preventScroll: true });
        }
      }
      if (ong) { $("minhas-reservas").hidden = false; carregarReservas(); }
  }
  document.addEventListener("reconecta:sessao", function (evento) { iniciar(evento.detail && evento.detail.usuario); });
  if (window.ReConecta && window.ReConecta.sessao) {
    window.ReConecta.sessao.then(iniciar);
  }
})();
