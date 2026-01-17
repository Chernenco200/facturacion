let chartVentasDia, chartVentasCat, chartLunasEnfoque, chartLunasMaterial, chartLunasTrat;
let chartBiseladoSerie, chartSLA, chartCaja;

function money(n){
  const x = Number(n || 0);
  return "S/ " + x.toFixed(2);
}

function setText(id, value){
  const el = document.getElementById(id);
  if(el) el.textContent = value;
}

function safeArr(x){ return Array.isArray(x) ? x : []; }

async function loadDashboard(){
  const preset = document.getElementById("preset").value;
  const url = `/dashboard/data/?preset=${encodeURIComponent(preset)}`;
  const res = await fetch(url);
  const data = await res.json();

  // Range
  setText("rangeLabel", `Rango: ${data.range.start} → ${data.range.end}`);

  // KPIs
  setText("kpiVentasHoy", money(data.kpis.hoy.ventas));
  setText("kpiTicketsHoy", String(data.kpis.hoy.tickets));
  setText("kpiSaldoHoy", money(data.kpis.hoy.saldo_pendiente));

  setText("kpiVentasMes", money(data.kpis.mes.ventas));
  setText("kpiTicketProm", money(data.kpis.mes.ticket_promedio));

  // Cobros hoy
  const cob = data.kpis.hoy.cobros || {};
  setText("cobroEF", money(cob.EFECTIVO || 0));
  setText("cobroYAPE", money(cob.YAPE || 0));
  setText("cobroPLIN", money(cob.PLIN || 0));
  setText("cobroTARJETA", money(cob.TARJETA || 0));
  setText("cobroTRANSFERENCIA", money(cob.TRANSFERENCIA || 0));

  // Ventas por día (línea)
  const vpd = safeArr(data.ventas_por_dia);
  const labels = vpd.map(x => x.date);
  const ventas = vpd.map(x => x.ventas);

  if(chartVentasDia) chartVentasDia.destroy();
  chartVentasDia = new Chart(document.getElementById("chartVentasDia"), {
    type: "line",
    data: { labels, datasets: [{ label: "Ventas", data: ventas }] },
    options: { responsive: true, maintainAspectRatio: false }
  });

  // Ventas por categoría (dona)
  const vc = safeArr(data.ventas_categoria);
  const catLabels = vc.map(x => x.categoria);
  const catVals = vc.map(x => x.monto);

  if(chartVentasCat) chartVentasCat.destroy();
  chartVentasCat = new Chart(document.getElementById("chartVentasCat"), {
    type: "doughnut",
    data: { labels: catLabels, datasets: [{ label: "Monto", data: catVals }] },
    options: { responsive: true, maintainAspectRatio: false }
  });

  // Lunas charts
  const lunas = data.lunas || {};
  setText("lunasNota", lunas.nota || "");

  function makeBarChart(canvasId, rows, title){
    const r = safeArr(rows);
    const L = r.map(x => (x.enfoque || x.material || x.tratamiento || "N/D"));
    const V = r.map(x => x.c);
    return new Chart(document.getElementById(canvasId), {
      type: "bar",
      data: { labels: L, datasets: [{ label: title, data: V }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: true } }
      }
    });
  }

  if(chartLunasEnfoque) chartLunasEnfoque.destroy();
  chartLunasEnfoque = makeBarChart("chartLunasEnfoque", lunas.enfoque, "Enfoque");

  if(chartLunasMaterial) chartLunasMaterial.destroy();
  chartLunasMaterial = makeBarChart("chartLunasMaterial", lunas.material, "Material");

  if(chartLunasTrat) chartLunasTrat.destroy();
  chartLunasTrat = makeBarChart("chartLunasTrat", lunas.tratamiento, "Tratamiento");

  // Taller / Biselado
  const bis = (data.taller && data.taller.biselado) ? data.taller.biselado : {};
  setText("biselAvg", String((bis.avg_min || 0).toFixed(1)));
  setText("biselMed", String((bis.median_min || 0).toFixed(1)));

  const bserie = safeArr(bis.serie);
  const bL = bserie.map(x => x.date);
  const bV = bserie.map(x => x.avg_min);

  if(chartBiseladoSerie) chartBiseladoSerie.destroy();
  chartBiseladoSerie = new Chart(document.getElementById("chartBiseladoSerie"), {
    type: "line",
    data: { labels: bL, datasets: [{ label: "Promedio min biselado", data: bV }] },
    options: { responsive: true, maintainAspectRatio: false }
  });

  // Tablas biselado
  const tblEn = document.getElementById("tblEnBiselado");
  tblEn.innerHTML = "";
  safeArr(bis.en_biselado).forEach(r => {
    tblEn.insertAdjacentHTML("beforeend",
      `<tr><td>${r.ticket}</td><td>${r.cliente}</td><td>${r.inicio}</td><td>${r.minutos}</td></tr>`
    );
  });

  const tblTop = document.getElementById("tblBiselTop");
  tblTop.innerHTML = "";
  safeArr(bis.top_lentas).forEach(r => {
    tblTop.insertAdjacentHTML("beforeend",
      `<tr><td>${r.ticket}</td><td>${r.cliente}</td><td>${r.minutos}</td></tr>`
    );
  });

  // SLA LISTO
  setText("slaATiempo", String(data.sla_listo.a_tiempo || 0));
  setText("slaTarde", String(data.sla_listo.tarde || 0));
  setText("slaProm", String((data.sla_listo.retraso_prom_min || 0).toFixed(1)));

  if(chartSLA) chartSLA.destroy();
  chartSLA = new Chart(document.getElementById("chartSLA"), {
    type: "doughnut",
    data: {
      labels: ["A tiempo", "Tarde"],
      datasets: [{ data: [data.sla_listo.a_tiempo || 0, data.sla_listo.tarde || 0] }]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });

  const tblSla = document.getElementById("tblSLATop");
  tblSla.innerHTML = "";
  safeArr(data.sla_listo.top_tardios).forEach(r => {
    tblSla.insertAdjacentHTML("beforeend",
      `<tr><td>${r.ticket}</td><td>${r.cliente}</td><td>${r.minutos_tarde}</td></tr>`
    );
  });

  // Inventario
  const tblCrit = document.getElementById("tblStockCrit");
  tblCrit.innerHTML = "";
  safeArr(data.inventario.stock_critico).forEach(r => {
    tblCrit.insertAdjacentHTML("beforeend",
      `<tr><td>${r.cod}</td><td>${r.descripcion}</td><td>${r.stock}</td></tr>`
    );
  });

  const tblVend = document.getElementById("tblTopVendidos");
  tblVend.innerHTML = "";
  safeArr(data.inventario.top_vendidos).forEach(r => {
    tblVend.insertAdjacentHTML("beforeend",
      `<tr><td>${r.producto__cod}</td><td>${r.producto__descripcion}</td><td>${r.cant}</td></tr>`
    );
  });

  // Caja chart
  setText("gastosRango", money(data.caja.gastos_rango || 0));
  const c = safeArr(data.caja.serie);
  const cL = c.map(x => x.date);
  const cIng = c.map(x => x.ingresos);
  const cEgr = c.map(x => x.egresos);

  if(chartCaja) chartCaja.destroy();
  chartCaja = new Chart(document.getElementById("chartCaja"), {
    type: "line",
    data: {
      labels: cL,
      datasets: [
        { label: "Ingresos", data: cIng },
        { label: "Egresos", data: cEgr }
      ]
    },
    options: { responsive: true, maintainAspectRatio: false }
  });

  // Cobranzas
  const tblDeu = document.getElementById("tblDeudores");
  tblDeu.innerHTML = "";
  safeArr(data.cobranzas.top_deudores).forEach(r => {
    tblDeu.insertAdjacentHTML("beforeend",
      `<tr><td>${r.cliente__nombre || ""}</td><td>${r.cliente__telefono || ""}</td><td>${money(r.saldo)}</td></tr>`
    );
  });
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("btnRefresh").addEventListener("click", loadDashboard);
  loadDashboard();
});
