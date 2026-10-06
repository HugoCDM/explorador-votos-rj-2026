// Keep-alive do Render - colocar em Apps Script
// 1. Crie um projeto em https://script.google.com
// 2. Cole esta funcao
// 3. Em Acionadores/Triggers -> adicionar -> "acionador orientado por tempo"
//    -> "Timer de minuto" -> "A cada 1 minuto"

var RENDER_URL = "https://explorador-votos-rj-2026.onrender.com/api/health";

function pingRender() {
  try {
    var res = UrlFetchApp.fetch(RENDER_URL, { muteHttpExceptions: true, timeoutSeconds: 30 });
    Logger.log(new Date() + " -> " + res.getResponseCode() + " " + res.getContentText());
  } catch (e) {
    Logger.log(new Date() + " -> ERRO: " + e);
  }
}