let chartsInst = {};

async function cargarDatos() {
    const params = {
        moneda: document.getElementById("moneda").value,
        top_n: document.getElementById("top_n").value,
        cliente_busqueda: document.getElementById("busqueda_cliente").value,
        prod_criterio: document.getElementById("prod_criterio")?.value || 'monto',
        fecha_inicio: document.getElementById("fecha_inicio")?.value || '',
        fecha_fin: document.getElementById("fecha_fin")?.value || '',
        vendedor: document.getElementById("vendedor")?.value || ''
    };

    try {
        const resp = await fetch("/api/ventas", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params)
        });
        const d = await resp.json();

        // Actualizar filtro de vendedores si existe la lista
        const selVend = document.getElementById("vendedor");
        if (selVend && d.lista_vendedores) {
            const actual = selVend.value;
            selVend.innerHTML = '<option value="">Todos los Vendedores</option>';
            d.lista_vendedores.forEach(v => {
                const opt = document.createElement("option");
                opt.value = v;
                opt.text = v;
                if (v === actual) opt.selected = true;
                selVend.appendChild(opt);
            });
        }

        // Gráfico de Productos (Pestaña Productos)
        const pData = params.prod_criterio === 'monto' ? d.productos.monto : d.productos.unid;
        
        // Renderizado optimizado para nombres largos
        renderChartVentas("chartProductos", 
            pData.map(x => x.PRODUCTO), 
            pData.map(x => x.V), 
            "#1abc9c", 
            params.prod_criterio === 'monto' ? 'Monto' : 'Unidades'
        );

        // Gráfico de Vendedores (Si existe el canvas)
        if (d.vendedores) {
            renderChartVentas("chartVendedores", 
                d.vendedores.map(x => x.label), 
                d.vendedores.map(x => x.value), 
                "#8e44ad", 
                "Ventas por Vendedor"
            );

            // Gráfico de Productos del Vendedor TOP 1
            if (d.vendedores.length > 0 && d.detalles_vendedor) {
                const topVend = d.vendedores[0].label;
                const prods = d.detalles_vendedor[topVend];
                renderChartVentas("chartVendedorTopProductos", 
                    prods.map(x => x.label), 
                    prods.map(x => x.value), 
                    "#e67e22", 
                    `Top Productos (${topVend})`
                );
            }
        }

    } catch (e) { console.error("Error en Ventas:", e); }
}

function renderChartVentas(id, labels, values, color, labelSet) {
    const canvas = document.getElementById(id);
    if (!canvas) return;
    if (chartsInst[id]) chartsInst[id].destroy();
    
    chartsInst[id] = new Chart(canvas.getContext('2d'), {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: labelSet,
                data: values,
                backgroundColor: color,
                borderRadius: 4,
                barPercentage: 0.6, // Barras más delgadas para dar aire al texto
                categoryPercentage: 0.8
            }]
        },
        options: {
            indexAxis: 'y', // Barras horizontales
            responsive: true,
            maintainAspectRatio: false,
            layout: {
                padding: {
                    left: 20 // Espacio extra de seguridad
                }
            },
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        autoSkip: false, // Obliga a mostrar todos los nombres
                        font: { size: 11 },
                        // Esta función recorta el nombre si es EXTREMADAMENTE largo, pero prioriza visibilidad
                        callback: function(value) {
                            const label = this.getLabelForValue(value);
                            return label.length > 30 ? label.substr(0, 27) + '...' : label;
                        }
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { font: { size: 10 } }
                }
            }
        }
    });
}