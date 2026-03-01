let instInv = {};

async function cargarInv() {
    try {
    const moneda = document.getElementById("moneda_inv").value;
    const r = await fetch("/api/inventario", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            moneda: moneda,
            producto: document.getElementById("inv_prod").value
        })
    });
    const d = await r.json();

        // KPIs
        document.getElementById("t_val").innerText = `${d.totales.monto_total.toLocaleString()} ${moneda}`;
        document.getElementById("t_art").innerText = d.totales.articulos;
        document.getElementById("t_exi").innerText = d.totales.existencia.toLocaleString();
        document.getElementById("t_val").innerText = d.totales.monto_total.toLocaleString();
        document.getElementById("t_kg").innerText = d.totales.kilos.toLocaleString();

        // Tabla
        const tbody = document.getElementById("tabla_inv");
        if (tbody) {
            tbody.innerHTML = d.tabla.map(i => `
                <tr>
                    <td>${i.CODIGO}</td>
                    <td>${i.DESCRIPCION}</td>
                    <td><span class="badge bg-light text-dark">${i.MARCA}</span></td>
                    <td class="text-end fw-bold">${i.EXISTENCIA}</td>
                    <td class="text-end text-success">${i.MONTO.toLocaleString()}</td>
                </tr>
            `).join("");
        }

        // Gráfico de Marcas
        renderInvChart("chartInvMarca", d.marcas_chart.map(x => x.MARCA), d.marcas_chart.map(x => x.V));

    } catch (e) { console.error("Error en Inventario:", e); }
}

function renderInvChart(id, labels, values) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (instInv[id]) instInv[id].destroy();

    instInv[id] = new Chart(canvas.getContext('2d'), {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: ['#3498db', '#2ecc71', '#f1c40f', '#e67e22', '#e74c3c', '#9b59b6']
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { position: 'bottom', labels: { boxWidth: 10 } } }
        }
    });
}

document.addEventListener("DOMContentLoaded", cargarInv);