/* Foto da validade: reduzida no navegador antes de enviar (oferta no painel e doação para pedido).
   Foto de celular passa fácil de 5 MB; aqui ela vira JPEG com o lado maior em até 1600 px.
   Redesenhar no canvas também tira os metadados (EXIF com GPS) do arquivo enviado. */
(function () {
  "use strict";
  var LADO = 1600, QUALIDADES = [0.8, 0.65, 0.5];
  var MAX = 5 * 1024 * 1024;
  var TIPOS = ["image/jpeg", "image/png", "image/webp"];

  function viaImagem(arquivo) {
    return new Promise(function (ok, falha) {
      var url = URL.createObjectURL(arquivo), img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); ok(img); };
      img.onerror = function () { URL.revokeObjectURL(url); falha(new Error("decodificar")); };
      img.src = url;
    });
  }
  function decodificar(arquivo) {
    // imageOrientation aplica a rotação do EXIF: a foto "em pé" do celular continua em pé
    if (window.createImageBitmap) {
      return createImageBitmap(arquivo, { imageOrientation: "from-image" })
        .catch(function () { return viaImagem(arquivo); });
    }
    return viaImagem(arquivo);
  }
  function codificar(canvas, qualidade) {
    return new Promise(function (ok, falha) {
      canvas.toBlob(function (blob) { blob ? ok(blob) : falha(new Error("codificar")); }, "image/jpeg", qualidade);
    });
  }
  function kb(bytes) {
    return bytes >= 1024 * 1024
      ? (bytes / 1024 / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 1 }) + " MB"
      : Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  /* Resolve {arquivo, largura, altura, tamanho, original}; rejeita com mensagem para o campo. */
  function preparar(arquivo) {
    if (!arquivo) return Promise.reject(new Error("Tire ou escolha uma foto do alimento mostrando a validade."));
    return decodificar(arquivo).then(function (img) {
      var largura = img.width, altura = img.height;
      var escala = Math.min(1, LADO / Math.max(largura, altura));
      var canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(largura * escala));
      canvas.height = Math.max(1, Math.round(altura * escala));
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";  // PNG transparente não fica preto no JPEG
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      if (img.close) img.close();
      var tentativa = 0;
      function proxima() {
        return codificar(canvas, QUALIDADES[tentativa]).then(function (blob) {
          if (blob.size > MAX && ++tentativa < QUALIDADES.length) return proxima();
          if (blob.size > MAX) throw new Error("A foto ficou maior que 5 MB. Tente outra foto.");
          return blob;
        });
      }
      return proxima().then(function (blob) {
        // nome neutro: o nome original do arquivo não sai do aparelho
        return { arquivo: new File([blob], "validade.jpg", { type: "image/jpeg" }),
                 largura: canvas.width, altura: canvas.height, tamanho: blob.size, original: arquivo.size };
      });
    }, function () {
      // o navegador não abriu a imagem (ex.: HEIC no computador): só segue se já for aceita
      if (TIPOS.indexOf(arquivo.type) !== -1 && arquivo.size <= MAX) {
        return { arquivo: arquivo, largura: null, altura: null, tamanho: arquivo.size, original: arquivo.size };
      }
      throw new Error("Não foi possível abrir esta foto. Use JPEG, PNG ou WebP.");
    });
  }
  function descrever(pronta) {
    if (!pronta.largura) return "Foto pronta · " + kb(pronta.tamanho);
    var texto = "Foto pronta · " + pronta.largura + " × " + pronta.altura + " px · " + kb(pronta.tamanho);
    return pronta.original > pronta.tamanho ? texto + " (era " + kb(pronta.original) + ")" : texto;
  }
  window.ReConectaFoto = { preparar: preparar, descrever: descrever, MAX: MAX, LADO: LADO };
})();
