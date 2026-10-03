/* ReConecta — cadastro de empresa (CNPJ) e doador (CPF).
   A validação aqui é só para a experiência; o servidor é a fonte da verdade. */
(function () {
  "use strict";

  var API = "/reconecta/cadastro";
  var ATRASO_CONSULTA_MS = 450;

  /* ---------- utilidades ---------- */

  function $(id) { return document.getElementById(id); }
  function digitos(valor) { return String(valor || "").replace(/\D+/g, ""); }

  function el(tag, attrs, filhos) {
    var no = document.createElement(tag);
    if (attrs) {
      Object.keys(attrs).forEach(function (k) {
        if (k === "texto") no.textContent = attrs[k];
        else if (k === "classe") no.className = attrs[k];
        else no.setAttribute(k, attrs[k]);
      });
    }
    (filhos || []).forEach(function (f) {
      if (f == null || f === "") return;
      no.appendChild(typeof f === "string" ? document.createTextNode(f) : f);
    });
    return no;
  }

  function icone(nome) {
    var caminhos = {
      alerta: '<path d="M12 3.5 2.8 19.5h18.4z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><path d="M12 10v4.2" stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/><circle cx="12" cy="17" r="1.1" fill="currentColor"/>',
      bloqueio: '<circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.8"/><path d="M5.8 18.2 18.2 5.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>',
      local: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="12" cy="10" r="2.3" fill="currentColor"/>'
    };
    var span = el("span", { "aria-hidden": "true" });
    span.innerHTML = '<svg viewBox="0 0 24 24" focusable="false" width="100%" height="100%">' + caminhos[nome] + "</svg>";
    return span.firstChild;
  }

  /* ---------- máscaras ---------- */

  function mascaraCNPJ(v) {
    var d = digitos(v).slice(0, 14);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  function mascaraCPF(v) {
    var d = digitos(v).slice(0, 11);
    return d
      .replace(/^(\d{3})(\d)/, "$1.$2")
      .replace(/^(\d{3})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1-$2");
  }

  function mascaraTelefone(v) {
    var d = digitos(v);
    if (d.length > 11 && d.charAt(0) === "0") d = d.slice(1);
    d = d.slice(0, 11);
    if (d.length <= 2) return d.length ? "(" + d : "";
    var ddd = d.slice(0, 2), resto = d.slice(2);
    var corte = d.length === 11 ? 5 : 4;
    if (resto.length <= corte) return "(" + ddd + ") " + resto;
    return "(" + ddd + ") " + resto.slice(0, corte) + "-" + resto.slice(corte);
  }

  function formatarCNAE(codigo) {
    var d = digitos(codigo).padStart(7, "0");
    return d.slice(0, 4) + "-" + d.slice(4, 5) + "/" + d.slice(5, 7);
  }

  /* Reaplica a máscara preservando a posição do cursor relativa aos dígitos. */
  function aplicarMascara(input, mascara) {
    var pos = input.selectionStart || 0;
    var digitosAntes = digitos(input.value.slice(0, pos)).length;
    input.value = mascara(input.value);
    if (document.activeElement !== input) return;
    var novaPos = 0, contados = 0;
    while (novaPos < input.value.length && contados < digitosAntes) {
      if (/\d/.test(input.value.charAt(novaPos))) contados++;
      novaPos++;
    }
    input.setSelectionRange(novaPos, novaPos);
  }

  /* ---------- validações (espelham o servidor) ---------- */

  function cnpjValido(valor) {
    var d = digitos(valor);
    if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false;
    function dv(base) {
      var pesos = base.length === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
      var soma = 0;
      for (var i = 0; i < base.length; i++) soma += Number(base.charAt(i)) * pesos[i];
      var r = soma % 11;
      return r < 2 ? 0 : 11 - r;
    }
    var d1 = dv(d.slice(0, 12));
    var d2 = dv(d.slice(0, 12) + d1);
    return d.slice(12) === String(d1) + String(d2);
  }

  function cpfValido(valor) {
    var d = digitos(valor);
    if (d.length !== 11 || /^(\d)\1{10}$/.test(d)) return false;
    for (var t = 9; t < 11; t++) {
      var soma = 0;
      for (var i = 0; i < t; i++) soma += Number(d.charAt(i)) * (t + 1 - i);
      var dv = (soma * 10) % 11 % 10;
      if (dv !== Number(d.charAt(t))) return false;
    }
    return true;
  }

  function emailValido(v) { return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(v).trim()); }
  function telefoneValido(v) { var n = digitos(v).length; return n === 10 || n === 11; }

  var MSG = {
    nome: "Informe seu nome completo (pelo menos 3 letras).",
    cpf: "Este CPF não é válido. Confira os números.",
    cpfVazio: "Informe seu CPF.",
    email: "Informe um e-mail válido, como nome@dominio.com.",
    telefone: "Informe o telefone com DDD (10 ou 11 dígitos).",
    cnpj: "Este CNPJ não é válido. Confira os números digitados.",
    cnpjIncompleto: "O CNPJ tem 14 dígitos.",
    senha: "A senha precisa de pelo menos 8 caracteres, com letra e número.",
    confirmar: "As senhas não são iguais."
  };

  function senhaValida(v) {
    return v.length >= 8 && /[A-Za-zÀ-ÖØ-öø-ÿ]/.test(v) && /\d/.test(v);
  }

  function nivelSenha(v) {
    if (!v) return 0;
    if (!senhaValida(v)) return 1;
    if (v.length >= 12 && /[^A-Za-zÀ-ÖØ-öø-ÿ\d]/.test(v)) return 3;
    return 2;
  }

  /* ---------- senha: medidor e mostrar/ocultar ---------- */

  function ligarSenha(inputSenha, inputConfirmar, medidor) {
    inputSenha.addEventListener("input", function () {
      medidor.setAttribute("data-nivel", String(nivelSenha(inputSenha.value)));
      if (inputSenha.getAttribute("aria-invalid") && senhaValida(inputSenha.value)) mostrarErro(inputSenha, "");
      if (inputConfirmar.getAttribute("aria-invalid") && inputConfirmar.value === inputSenha.value) mostrarErro(inputConfirmar, "");
    });
    inputSenha.addEventListener("blur", function () {
      if (inputSenha.value) mostrarErro(inputSenha, senhaValida(inputSenha.value) ? "" : MSG.senha);
    });
    inputConfirmar.addEventListener("input", function () {
      if (inputConfirmar.getAttribute("aria-invalid") && inputConfirmar.value === inputSenha.value) mostrarErro(inputConfirmar, "");
    });
    inputConfirmar.addEventListener("blur", function () {
      if (inputConfirmar.value) mostrarErro(inputConfirmar, inputConfirmar.value === inputSenha.value ? "" : MSG.confirmar);
    });
  }

  document.querySelectorAll("[data-olho]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var alvo = $(btn.getAttribute("data-olho"));
      if (!alvo) return;
      var mostrar = alvo.type === "password";
      alvo.type = mostrar ? "text" : "password";
      btn.setAttribute("aria-pressed", mostrar ? "true" : "false");
      btn.setAttribute("aria-label", mostrar ? "Ocultar senha" : "Mostrar senha");
      alvo.focus();
    });
  });

  /* ---------- erros de campo ---------- */

  function erroDoCampo(input) { return $(input.id + "-erro"); }

  function mostrarErro(input, mensagem) {
    var alvo = erroDoCampo(input);
    if (mensagem) {
      input.setAttribute("aria-invalid", "true");
      input.classList.remove("is-valido");
      if (alvo) alvo.textContent = mensagem;
    } else {
      input.removeAttribute("aria-invalid");
      if (alvo) alvo.textContent = "";
    }
  }

  function limparErros(form) {
    form.querySelectorAll("[aria-invalid]").forEach(function (i) { i.removeAttribute("aria-invalid"); });
    form.querySelectorAll("[data-erro]").forEach(function (p) { p.textContent = ""; });
  }

  function mostrarAviso(caixa, titulo, texto, opcoes) {
    opcoes = opcoes || {};
    caixa.replaceChildren();
    caixa.className = "aviso" + (opcoes.erro ? " aviso--erro" : "");
    var corpo = el("div", null, [
      el("p", { classe: "aviso__titulo", texto: titulo }),
      texto ? el("p", { classe: "aviso__texto", texto: texto }) : null
    ]);
    if (opcoes.acao) {
      var b = el("button", { type: "button", classe: "botao botao--secundario", texto: opcoes.acao.rotulo });
      b.addEventListener("click", opcoes.acao.fn);
      corpo.appendChild(b);
    }
    var ic = icone(opcoes.erro ? "bloqueio" : "alerta");
    ic.setAttribute("class", "aviso__icone");
    caixa.append(ic, corpo);
    caixa.hidden = false;
    return caixa;
  }

  function esconderAviso(caixa) { caixa.hidden = true; caixa.replaceChildren(); }

  function aplicarCampos(form, campos, mapa) {
    var primeiro = null;
    Object.keys(campos || {}).forEach(function (nome) {
      var input = mapa[nome];
      if (!input) return;
      mostrarErro(input, campos[nome]);
      if (!primeiro) primeiro = input;
    });
    if (primeiro) primeiro.focus();
    return primeiro;
  }

  function carregando(botao, sim) {
    botao.classList.toggle("is-carregando", sim);
    botao.setAttribute("aria-busy", sim ? "true" : "false");
    if (sim) botao.disabled = true;
  }

  /* ---------- HTTP ---------- */

  function requisitar(url, opcoes) {
    return fetch(url, opcoes).then(function (resp) {
      return resp.text().then(function (texto) {
        var corpo = null;
        try { corpo = texto ? JSON.parse(texto) : null; } catch (e) { corpo = null; }
        return { status: resp.status, ok: resp.ok, corpo: corpo || {} };
      });
    });
  }

  function postar(caminho, dados) {
    return requisitar(API + caminho, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(dados)
    });
  }

  /* ---------- escolha de perfil ---------- */

  var formEmpresa = $("form-empresa");
  var formDoador = $("form-doador");
  var dicaPerfil = $("dica-perfil");

  /* Etapa 1: escolher o perfil e "Continuar". Etapa 2: o formulário do perfil, com "Voltar".
     Os dados digitados ficam guardados ao voltar e trocar de perfil. */
  var etapaPerfil = $("etapa-perfil");
  var btnContinuar = $("btn-continuar");
  var btnVoltar = $("btn-voltar");
  var radiosPerfil = document.querySelectorAll('input[name="perfil"]');
  var DICA_PADRAO = "Selecione uma opção acima para continuar.";

  function perfilEscolhido() {
    var r = document.querySelector('input[name="perfil"]:checked');
    return r ? r.value : null;
  }

  function irParaFormulario() {
    var perfil = perfilEscolhido();
    if (!perfil) {
      dicaPerfil.textContent = "Escolha se você é empresa ou doador para continuar.";
      dicaPerfil.classList.add("dica-perfil--alerta");
      radiosPerfil[0].focus();
      return;
    }
    etapaPerfil.hidden = true;
    btnVoltar.hidden = false;
    formEmpresa.hidden = perfil !== "empresa";
    formDoador.hidden = perfil !== "doador";
    var titulo = $(perfil === "empresa" ? "titulo-empresa" : "titulo-doador");
    titulo.focus();
    titulo.scrollIntoView({ block: "nearest" });
  }

  function voltarParaPerfil() {
    formEmpresa.hidden = true;
    formDoador.hidden = true;
    btnVoltar.hidden = true;
    etapaPerfil.hidden = false;
    $("cadastro-titulo").focus();
  }

  radiosPerfil.forEach(function (radio) {
    radio.addEventListener("change", function () {
      if (!radio.checked) return;
      dicaPerfil.classList.remove("dica-perfil--alerta");
      dicaPerfil.textContent = radio.value === "empresa"
        ? "Empresa selecionada. Na próxima etapa conferimos o CNPJ na Receita Federal."
        : "Doador selecionado. Na próxima etapa você informa nome, CPF e contato.";
    });
    // Enter no radio avança, como o botão Continuar
    radio.addEventListener("keydown", function (e) {
      if (e.key === "Enter") { e.preventDefault(); if (!radio.checked) radio.click(); irParaFormulario(); }
    });
  });
  btnContinuar.addEventListener("click", irParaFormulario);
  btnVoltar.addEventListener("click", voltarParaPerfil);

  // passo 1 da coluna esquerda leva ao início do cadastro
  var passoCadastro = $("passo-cadastro");
  if (passoCadastro) passoCadastro.addEventListener("click", function (e) {
    if (etapaSucesso && !etapaSucesso.hidden) return;
    e.preventDefault();
    if (etapaPerfil.hidden) { var f = formEmpresa.hidden ? formDoador : formEmpresa; f.querySelector(".formulario__titulo").focus(); }
    else $("cadastro-titulo").focus();
    $("conteudo").scrollIntoView({ behavior: "smooth", block: "start" });
  });
  // passo 2: quem já é empresa logada publica pelo painel; os demais entram primeiro
  document.addEventListener("reconecta:sessao", function (e) {
    var u = e.detail && e.detail.usuario;
    var p = $("passo-publicar");
    if (p) p.href = u && u.tipo === "empresa" ? "/painel" : "/entrar";
  });

  /* ---------- empresa ---------- */

  var cnpjInput = $("cnpj");
  var btnVerificar = $("btn-verificar");
  var resultado = $("resultado-cnpj");
  var contato = $("contato-empresa");
  var acessoEmpresa = $("acesso-empresa");
  var emailEmpresa = $("empresa-email");
  var telEmpresa = $("empresa-telefone");
  var senhaEmpresa = $("empresa-senha");
  var confirmarEmpresa = $("empresa-confirmar");
  var btnEmpresa = $("btn-empresa");
  var notaEmpresa = $("nota-empresa");
  var avisoEmpresa = $("aviso-empresa");

  ligarSenha(senhaEmpresa, confirmarEmpresa, $("empresa-senha-forca"));

  var consultaAtual = null;     // AbortController da consulta em andamento
  var temporizador = null;
  var empresaVerificada = null; // resposta 200 apta, com o CNPJ que a gerou

  function travarEmpresa(nota) {
    empresaVerificada = null;
    contato.disabled = true;
    acessoEmpresa.disabled = true;
    btnEmpresa.disabled = true;
    notaEmpresa.hidden = false;
    notaEmpresa.textContent = nota || "Verifique o CNPJ para liberar o cadastro.";
  }

  function liberarEmpresa(dados) {
    empresaVerificada = dados;
    contato.disabled = false;
    acessoEmpresa.disabled = false;
    btnEmpresa.disabled = false;
    notaEmpresa.hidden = true;
    if (!emailEmpresa.value && dados.email) emailEmpresa.value = String(dados.email).toLowerCase();
    if (!telEmpresa.value && dados.telefone) telEmpresa.value = mascaraTelefone(dados.telefone);
  }

  function cancelarConsulta() {
    clearTimeout(temporizador);
    if (consultaAtual) { consultaAtual.abort(); consultaAtual = null; }
    resultado.setAttribute("aria-busy", "false");
    btnVerificar.disabled = false;
  }

  function renderConsultando() {
    resultado.setAttribute("aria-busy", "true");
    resultado.replaceChildren(el("div", { classe: "consulta" }, [
      el("span", { classe: "consulta__spinner", "aria-hidden": "true" }),
      el("p", { classe: "consulta__texto", texto: "Consultando na Receita Federal…" }),
      el("div", { classe: "consulta__esqueleto", "aria-hidden": "true" }, [el("span"), el("span"), el("span")])
    ]));
  }

  function cartaoEmpresa(d, apta) {
    var situacao = String(d.situacao || (d.ativo ? "ATIVA" : "INATIVA")).toUpperCase();
    var local = [d.endereco && d.endereco.municipio, d.endereco && d.endereco.uf].filter(Boolean).join(" / ");
    var nomeFantasia = d.nome_fantasia && d.nome_fantasia !== d.razao_social ? d.nome_fantasia : "";

    var topo = el("div", { classe: "empresa__topo" }, [
      el("div", { classe: "empresa__linha-selo" }, [
        el("span", { classe: "empresa__cnpj", texto: d.cnpj_formatado || mascaraCNPJ(d.cnpj) }),
        el("span", { classe: "selo " + (d.ativo ? "selo--ativa" : "selo--inativa"), texto: situacao })
      ]),
      el("p", { classe: "empresa__nome", texto: d.razao_social || "Empresa sem razão social informada" }),
      nomeFantasia ? el("p", { classe: "empresa__fantasia", texto: nomeFantasia }) : null
    ]);
    if (local) {
      var ic = icone("local");
      topo.appendChild(el("p", { classe: "empresa__local" }, [ic, local]));
    }

    var cartao = el("article", {
      classe: "empresa " + (apta ? "empresa--apta" : "empresa--recusada"),
      "aria-label": apta ? "Empresa verificada" : "Empresa não pode ser cadastrada"
    }, [topo]);

    var atividades = d.atividades_alimentares || [];
    if (apta && atividades.length) {
      cartao.appendChild(el("div", { classe: "empresa__secao" }, [
        el("p", { classe: "empresa__secao-titulo", texto: "Atividades no setor de alimentos" }),
        el("ul", { classe: "atividades" }, atividades.map(function (a) {
          return el("li", { classe: "atividade" }, [
            el("span", { classe: "atividade__categoria", texto: a.categoria || "Alimentação" }),
            el("span", { classe: "atividade__descricao", texto: a.descricao ? formatarCNAE(a.codigo) + " · " + a.descricao : formatarCNAE(a.codigo) })
          ]);
        }))
      ]));
    }

    if (!apta) {
      var motivos = (d.motivos && d.motivos.length) ? d.motivos : [{ codigo: "", mensagem: "Esta empresa não atende aos requisitos de cadastro." }];
      cartao.appendChild(el("div", { classe: "empresa__secao" }, [
        el("p", { classe: "empresa__secao-titulo", texto: "Por que não podemos seguir" }),
        el("ul", { classe: "motivos" }, motivos.map(function (m) { return itemMotivo(m, d); }))
      ]));
    }
    return cartao;
  }

  function itemMotivo(m, d) {
    var extra = null;
    if (m.codigo === "SEM_RELACAO_ALIMENTAR") {
      extra = el("p", { classe: "motivo__extra" }, [
        "O ReConecta é exclusivo para quem produz, vende ou serve alimentos. "
      ]);
      if (d.cnae_principal && d.cnae_principal.descricao) {
        extra.append("Atividade principal na Receita: ",
          el("strong", { texto: d.cnae_principal.descricao }), " ",
          el("span", { classe: "motivo__cnae", texto: "(" + formatarCNAE(d.cnae_principal.codigo) + ")" }), ".");
      }
    } else if (m.codigo === "CNPJ_INATIVO") {
      extra = el("p", { classe: "motivo__extra", texto: "Só aceitamos CNPJ com situação ATIVA. Se a situação mudou há pouco, a Receita pode levar alguns dias para atualizar." });
    } else if (m.codigo === "CNPJ_JA_CADASTRADO") {
      extra = el("p", { classe: "motivo__extra", texto: "Se a empresa é sua e você não fez esse cadastro, fale com a equipe do ReConecta." });
    }
    var ic = icone(m.codigo === "SEM_RELACAO_ALIMENTAR" ? "bloqueio" : "alerta");
    ic.setAttribute("class", "motivo__icone");
    return el("li", { classe: "motivo" }, [ic, el("div", null, [el("p", { classe: "motivo__msg", texto: m.mensagem }), extra])]);
  }

  function renderAvisoConsulta(titulo, texto, comRetry) {
    var caixa = el("div");
    mostrarAviso(caixa, titulo, texto, {
      erro: !comRetry,
      acao: comRetry ? { rotulo: "Tentar novamente", fn: function () { consultarCNPJ(true); } } : null
    });
    resultado.replaceChildren(caixa);
  }

  function consultarCNPJ(imediato) {
    var cnpj = digitos(cnpjInput.value);
    cancelarConsulta();
    esconderAviso(avisoEmpresa);

    if (cnpj.length !== 14) {
      mostrarErro(cnpjInput, cnpj.length ? MSG.cnpjIncompleto : "Informe o CNPJ da empresa.");
      if (imediato) cnpjInput.focus();
      return;
    }
    if (!cnpjValido(cnpj)) { mostrarErro(cnpjInput, MSG.cnpj); return; }
    mostrarErro(cnpjInput, "");

    var executar = function () {
      var controle = new AbortController();
      consultaAtual = controle;
      btnVerificar.disabled = true;
      travarEmpresa("Aguardando a consulta do CNPJ…");
      renderConsultando();

      requisitar(API + "/cnpj/" + cnpj, { headers: { "Accept": "application/json" }, signal: controle.signal })
        .then(function (r) {
          if (consultaAtual !== controle) return;
          tratarConsulta(r, cnpj);
        })
        .catch(function (e) {
          if (e && e.name === "AbortError") return;
          if (consultaAtual !== controle) return;
          travarEmpresa();
          renderAvisoConsulta("Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", true);
        })
        .then(function () {
          if (consultaAtual === controle) {
            consultaAtual = null;
            resultado.setAttribute("aria-busy", "false");
            btnVerificar.disabled = false;
          }
        });
    };

    if (imediato) executar();
    else temporizador = setTimeout(executar, ATRASO_CONSULTA_MS);
  }

  function tratarConsulta(r, cnpj) {
    var c = r.corpo;
    if (r.status === 200) {
      cnpjInput.classList.toggle("is-valido", !!c.apto);
      resultado.replaceChildren(cartaoEmpresa(c, !!c.apto));
      if (c.apto) liberarEmpresa(c);
      else travarEmpresa("Esta empresa não pode ser cadastrada.");
      return;
    }
    travarEmpresa();
    if (r.status === 400) {
      resultado.replaceChildren();
      mostrarErro(cnpjInput, c.mensagem || MSG.cnpj);
    } else if (r.status === 404) {
      renderAvisoConsulta("CNPJ não encontrado na Receita Federal",
        c.mensagem || "Confira se o número " + mascaraCNPJ(cnpj) + " está certo.", false);
    } else if (r.status === 503) {
      renderAvisoConsulta("A consulta à Receita está indisponível agora",
        c.mensagem || "Os serviços de consulta não responderam. Isso costuma passar em instantes.", true);
    } else {
      renderAvisoConsulta("Algo deu errado na consulta",
        c.mensagem || "Tente novamente em alguns instantes.", true);
    }
  }

  cnpjInput.addEventListener("input", function () {
    aplicarMascara(cnpjInput, mascaraCNPJ);
    var cnpj = digitos(cnpjInput.value);
    cnpjInput.classList.remove("is-valido");
    if (empresaVerificada && empresaVerificada.cnpj !== cnpj) travarEmpresa();
    cancelarConsulta();
    if (cnpj.length < 14) {
      resultado.replaceChildren();
      mostrarErro(cnpjInput, "");
      travarEmpresa();
      return;
    }
    consultarCNPJ(false);
  });

  cnpjInput.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { e.preventDefault(); consultarCNPJ(true); }
  });

  btnVerificar.addEventListener("click", function () { consultarCNPJ(true); });

  telEmpresa.addEventListener("input", function () { aplicarMascara(telEmpresa, mascaraTelefone); });
  emailEmpresa.addEventListener("blur", function () {
    if (emailEmpresa.value) mostrarErro(emailEmpresa, emailValido(emailEmpresa.value) ? "" : MSG.email);
  });
  telEmpresa.addEventListener("blur", function () {
    if (telEmpresa.value) mostrarErro(telEmpresa, telefoneValido(telEmpresa.value) ? "" : MSG.telefone);
  });

  formEmpresa.addEventListener("submit", function (e) {
    e.preventDefault();
    if (!empresaVerificada) { consultarCNPJ(true); return; }
    esconderAviso(avisoEmpresa);
    mostrarErro(emailEmpresa, ""); mostrarErro(telEmpresa, "");
    mostrarErro(senhaEmpresa, ""); mostrarErro(confirmarEmpresa, "");

    var campos = {};
    if (!emailValido(emailEmpresa.value)) campos.email = MSG.email;
    if (!telefoneValido(telEmpresa.value)) campos.telefone = MSG.telefone;
    if (!senhaValida(senhaEmpresa.value)) campos.senha = MSG.senha;
    var mapa = { email: emailEmpresa, telefone: telEmpresa, cnpj: cnpjInput, senha: senhaEmpresa };
    if (confirmarEmpresa.value !== senhaEmpresa.value) {
      mostrarErro(confirmarEmpresa, MSG.confirmar);
      if (!Object.keys(campos).length) { confirmarEmpresa.focus(); return; }
    }
    if (Object.keys(campos).length) { aplicarCampos(formEmpresa, campos, mapa); return; }

    carregando(btnEmpresa, true);
    postar("/empresa", {
      cnpj: empresaVerificada.cnpj,
      email: emailEmpresa.value.trim(),
      telefone: digitos(telEmpresa.value),
      senha: senhaEmpresa.value
    }).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) { mostrarSucesso(c); return; }
      if (r.status === 400 && c.codigo === "DADOS_INVALIDOS") {
        aplicarCampos(formEmpresa, c.campos, mapa);
        if (!c.campos || !Object.keys(c.campos).length) mostrarAviso(avisoEmpresa, "Confira os dados", c.mensagem, { erro: true });
      } else if (r.status === 400) {
        mostrarErro(cnpjInput, c.mensagem || MSG.cnpj); travarEmpresa(); resultado.replaceChildren(); cnpjInput.focus();
      } else if (r.status === 409 && c.codigo === "EMAIL_JA_CADASTRADO") {
        mostrarErro(emailEmpresa, c.mensagem || "Este e-mail já está em uso em outro cadastro."); emailEmpresa.focus();
      } else if (r.status === 409) {
        var dados = Object.assign({}, empresaVerificada, {
          apto: false,
          motivos: [{ codigo: "CNPJ_JA_CADASTRADO", mensagem: c.mensagem || "Este CNPJ já está cadastrado no ReConecta." }]
        });
        resultado.replaceChildren(cartaoEmpresa(dados, false));
        travarEmpresa("Esta empresa não pode ser cadastrada.");
      } else if (r.status === 422) {
        var recusada = Object.assign({}, empresaVerificada, { apto: false, motivos: c.motivos || [] });
        resultado.replaceChildren(cartaoEmpresa(recusada, false));
        travarEmpresa("Esta empresa não pode ser cadastrada.");
      } else if (r.status === 404) {
        mostrarAviso(avisoEmpresa, "CNPJ não encontrado na Receita Federal", c.mensagem, { erro: true });
      } else if (r.status === 503) {
        mostrarAviso(avisoEmpresa, "A consulta à Receita está indisponível agora",
          c.mensagem || "Seus dados não foram perdidos. Tente concluir de novo em instantes.",
          { acao: { rotulo: "Tentar novamente", fn: function () { formEmpresa.requestSubmit(); } } });
      } else {
        mostrarAviso(avisoEmpresa, "Não foi possível concluir o cadastro", c.mensagem || "Tente novamente em alguns instantes.", { erro: true });
      }
    }).catch(function () {
      mostrarAviso(avisoEmpresa, "Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", {
        acao: { rotulo: "Tentar novamente", fn: function () { formEmpresa.requestSubmit(); } }
      });
    }).then(function () {
      carregando(btnEmpresa, false);
      btnEmpresa.disabled = !empresaVerificada;
    });
  });

  /* ---------- doador ---------- */

  var nomeDoador = $("doador-nome");
  var cpfDoador = $("doador-cpf");
  var emailDoador = $("doador-email");
  var telDoador = $("doador-telefone");
  var senhaDoador = $("doador-senha");
  var confirmarDoador = $("doador-confirmar");
  var btnDoador = $("btn-doador");
  var avisoDoador = $("aviso-doador");
  var mapaDoador = { nome: nomeDoador, cpf: cpfDoador, email: emailDoador, telefone: telDoador, senha: senhaDoador };

  ligarSenha(senhaDoador, confirmarDoador, $("doador-senha-forca"));

  function validarDoador(campo) {
    var v = {
      nome: function () { return nomeDoador.value.trim().length >= 3 ? "" : MSG.nome; },
      cpf: function () {
        if (!digitos(cpfDoador.value)) return MSG.cpfVazio;
        return cpfValido(cpfDoador.value) ? "" : MSG.cpf;
      },
      email: function () { return emailValido(emailDoador.value) ? "" : MSG.email; },
      telefone: function () { return telefoneValido(telDoador.value) ? "" : MSG.telefone; },
      senha: function () { return senhaValida(senhaDoador.value) ? "" : MSG.senha; }
    };
    return v[campo]();
  }

  cpfDoador.addEventListener("input", function () {
    aplicarMascara(cpfDoador, mascaraCPF);
    var n = digitos(cpfDoador.value).length;
    if (n === 11) {
      var erro = validarDoador("cpf");
      mostrarErro(cpfDoador, erro);
      cpfDoador.classList.toggle("is-valido", !erro);
    } else {
      cpfDoador.classList.remove("is-valido");
      if (cpfDoador.getAttribute("aria-invalid")) mostrarErro(cpfDoador, "");
    }
  });
  telDoador.addEventListener("input", function () { aplicarMascara(telDoador, mascaraTelefone); });

  Object.keys(mapaDoador).forEach(function (campo) {
    var input = mapaDoador[campo];
    input.addEventListener("blur", function () {
      if (input.value.trim()) mostrarErro(input, validarDoador(campo));
    });
    if (campo !== "cpf") {
      input.addEventListener("input", function () {
        if (input.getAttribute("aria-invalid") && !validarDoador(campo)) mostrarErro(input, "");
      });
    }
  });

  formDoador.addEventListener("submit", function (e) {
    e.preventDefault();
    esconderAviso(avisoDoador);
    limparErros(formDoador);

    var campos = {};
    Object.keys(mapaDoador).forEach(function (c) { var m = validarDoador(c); if (m) campos[c] = m; });
    if (confirmarDoador.value !== senhaDoador.value) mostrarErro(confirmarDoador, MSG.confirmar);
    if (Object.keys(campos).length) { aplicarCampos(formDoador, campos, mapaDoador); return; }
    if (confirmarDoador.value !== senhaDoador.value) { confirmarDoador.focus(); return; }

    carregando(btnDoador, true);
    postar("/doador", {
      nome: nomeDoador.value.trim(),
      cpf: digitos(cpfDoador.value),
      email: emailDoador.value.trim(),
      telefone: digitos(telDoador.value),
      senha: senhaDoador.value
    }).then(function (r) {
      var c = r.corpo;
      if (r.status === 201) { mostrarSucesso(c); return; }
      if (r.status === 400 && c.campos && Object.keys(c.campos).length) {
        aplicarCampos(formDoador, c.campos, mapaDoador);
      } else if (r.status === 409 && c.codigo === "CPF_JA_CADASTRADO") {
        mostrarErro(cpfDoador, c.mensagem || "Este CPF já está cadastrado."); cpfDoador.focus();
      } else if (r.status === 409 && c.codigo === "EMAIL_JA_CADASTRADO") {
        mostrarErro(emailDoador, c.mensagem || "Este e-mail já está em uso em outro cadastro."); emailDoador.focus();
      } else {
        mostrarAviso(avisoDoador, "Não foi possível concluir o cadastro", c.mensagem || "Tente novamente em alguns instantes.", { erro: r.status < 500 });
      }
    }).catch(function () {
      mostrarAviso(avisoDoador, "Não conseguimos falar com o servidor", "Verifique sua conexão e tente de novo.", {
        acao: { rotulo: "Tentar novamente", fn: function () { formDoador.requestSubmit(); } }
      });
    }).then(function () {
      carregando(btnDoador, false);
      btnDoador.disabled = false;
    });
  });

  /* ---------- sucesso ---------- */

  var etapaCadastro = $("etapa-cadastro");
  var etapaSucesso = $("etapa-sucesso");

  function mostrarSucesso(c) {
    var empresa = c.tipo === "empresa";
    $("sucesso-tipo").textContent = empresa ? "Empresa doadora" : "Doador";
    $("sucesso-texto").textContent = empresa
      ? "Sua empresa já faz parte da rede. Agora é só publicar os excedentes quando tiver alimento para doar."
      : "Obrigado por fazer parte. Avisaremos você por e-mail sobre as próximas ações de doação.";

    var linhas = [["Nome", c.nome]];
    if (empresa) {
      linhas.push(["CNPJ", c.cnpj_formatado || mascaraCNPJ(c.cnpj)]);
      if (c.endereco) linhas.push(["Endereço", c.endereco]);
    } else {
      linhas.push(["CPF", c.cpf_formatado]);
    }
    linhas.push(["E-mail", c.email]);
    if (c.telefone) linhas.push(["Telefone", mascaraTelefone(c.telefone)]);

    var dl = $("sucesso-dados");
    dl.replaceChildren();
    linhas.forEach(function (l) {
      if (!l[1]) return;
      dl.append(el("dt", { texto: l[0] }), el("dd", { texto: l[1] }));
    });

    etapaCadastro.hidden = true;
    etapaSucesso.hidden = false;
    etapaSucesso.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  $("btn-novo").addEventListener("click", function () {
    cancelarConsulta();
    formEmpresa.reset(); formDoador.reset();
    limparErros(formEmpresa); limparErros(formDoador);
    [cnpjInput, cpfDoador].forEach(function (i) { i.classList.remove("is-valido"); });
    ["empresa-senha-forca", "doador-senha-forca"].forEach(function (id) {
      $(id).removeAttribute("data-nivel");
    });
    document.querySelectorAll("[data-olho]").forEach(function (b) {
      var alvo = $(b.getAttribute("data-olho"));
      if (alvo) alvo.type = "password";
      b.setAttribute("aria-pressed", "false");
      b.setAttribute("aria-label", "Mostrar senha");
    });
    resultado.replaceChildren();
    esconderAviso(avisoEmpresa); esconderAviso(avisoDoador);
    travarEmpresa();
    document.querySelectorAll('input[name="perfil"]').forEach(function (r) { r.checked = false; });
    formEmpresa.hidden = true; formDoador.hidden = true;
    dicaPerfil.textContent = DICA_PADRAO; dicaPerfil.classList.remove("dica-perfil--alerta");
    etapaPerfil.hidden = false; btnVoltar.hidden = true;
    etapaSucesso.hidden = true;
    etapaCadastro.hidden = false;
    $("cadastro-titulo").focus();
  });

  travarEmpresa();
})();
