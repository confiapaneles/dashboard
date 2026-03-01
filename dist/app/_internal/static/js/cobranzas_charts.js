let chartsCob = {};

async function cargarCobranzas() {
    const p = {
        fecha_inicio: document.getElementById("f_ini_cob").value,
        fecha_fin: document.getElementById("f_fin_cob").value,
        moneda: document.getElementById("moneda_cob").value
    };

    try {
        const r = await fetch("/api/cobranzas", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(p)
        });
        const d = await r.json();

        // Actualizar KPIs
        document.getElementById("total_cobranza").innerText = `${d.total_general.toLocaleString()} ${p.moneda}`;
        document.getElementById("kpi_ticket").innerText = `${d.ticket_promedio.toLocaleString()} ${p.moneda}`;
        document.getElementById("kpi_conteo").innerText = d.conteo.toLocaleString();
        document.getElementById("kpi_metodo").innerText = d.formas_pago.length > 0 ? d.formas_pago[0].FORMA : "---";

        // Lista de porcentajes detallada
        const divPct = document.getElementById("lista_porcentajes");
        if (divPct) {
            divPct.innerHTML = d.formas_pago.map(f => `
                <div class="d-flex justify-content-between small px-2 border-bottom py-1">
                    <span>${f.FORMA}</span>
                    <span class="fw-bold">${f.P}%</span>
                </div>
            `).join("");
        }

        // Gráfico de Torta (Composición)
        renderCob("chartFormasPago", "doughnut", d.formas_pago.map(x => x.FORMA), d.formas_pago.map(x => x.V), 
                  ['#9b59b6', '#8e44ad', '#a569bd', '#bb8fce', '#d2b4de']);

        // Gráfico de Línea (Evolución Temporal)
        renderCob("chartCobranzaDiaria", "line", d.historico.map(x => x.F), d.historico.map(x => x.V), '#9b59b6');

    } catch (e) { console.error("Error en Cobranzas:", e); }
}

function renderCob(id, type, labels, values, colors) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (chartsCob[id]) chartsCob[id].destroy();
    
    chartsCob[id] = new Chart(ctx, {
        type: type,
        data: {
            labels: labels,
            datasets: [{
                label: 'Monto',
                data: values,
                backgroundColor: colors,
                borderColor: type === 'line' ? '#9b59b6' : '#fff',
                fill: type === 'line' ? { target: 'origin', above: 'rgba(155, 89, 182, 0.1)' } : false,
                tension: 0.4,
                pointRadius: 4
            }]
        },
        options: { 
            responsive: true, 
            maintainAspectRatio: false,
            plugins: { 
                legend: { 
                    display: type === 'doughnut', 
                    position: 'bottom',
                    labels: { boxWidth: 12, font: { size: 10 } }
                } 
            },
            scales: type === 'line' ? {
                y: { beginAtZero: true, grid: { color: '#f0f0f0' } },
                x: { grid: { display: false } }
            } : {}
        }
    });
}

document.addEventListener("DOMContentLoaded", cargarCobranzas);