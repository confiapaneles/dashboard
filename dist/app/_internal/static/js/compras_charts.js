let instCompras = {};

function paletaCompras(cant) {
    return Array.from({length: cant}, (_, i) => `hsla(${25 + i * (20/cant)}, 70%, 50%, 0.8)`);
}

async function cargarCompras() {
    const p = {
        fecha_inicio: document.getElementById("f_inicio").value,
        fecha_fin: document.getElementById("f_fin").value,
        moneda: document.getElementById("moneda_comp").value, // Asegurar ID correcto
        top_n: 10
    };

    const r = await fetch("/api/compras", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(p)
    });
    const d = await r.json();

    // Sumar Contado + Crédito para el total visual
    const sumaTotal = (d.totales.Contado || 0) + (d.totales.Credito || 0);
    document.getElementById("txt_total").innerText = `${sumaTotal.toLocaleString()} ${p.moneda}`;

    // Gráfico Tipo Compra (Arreglando leyenda undefined)
    renderComp("chartTipo", "bar", "Monto Total", 
        ["Contado", "Crédito"], 
        [d.totales.Contado || 0, d.totales.Credito || 0], 
        'x', ["#e67e22", "#d35400"]);

    // Proveedores y Productos en sus pestañas correspondientes
    renderComp("chartProv", "bar", "Top Proveedores", d.proveedores.map(x => x.PROVEEDOR), d.proveedores.map(x => x.V), 'y', "#f39c12");
    renderComp("chartProd", "bar", "Top Productos", d.productos_monto.map(x => x.PRODUCTO), d.productos_monto.map(x => x.V), 'y', "#d35400");
}

function renderComp(id, type, label, labels, values, axis, colors) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (instCompras[id]) instCompras[id].destroy();
    
    instCompras[id] = new Chart(canvas.getContext('2d'), {
        type: type,
        data: { 
            labels: labels, 
            datasets: [{ label: label, data: values, backgroundColor: colors, borderRadius: 5 }] 
        },
        options: { 
            indexAxis: axis, 
            responsive: true, 
            maintainAspectRatio: false,
            plugins: { 
                legend: { display: type === 'pie', position: 'bottom' } 
            },
            scales: type !== 'pie' ? {
                [axis === 'y' ? 'x' : 'y']: { beginAtZero: true }
            } : {}
        }
    });
}

document.addEventListener("DOMContentLoaded", cargarCompras);