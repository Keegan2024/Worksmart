async function fetchClients(){
    const res = await fetch('/api/clients');
    if(res.status === 200){
        const data = await res.json();
        renderClients(data);
        updateStats(data);
    } else if(res.status === 401){
        window.location.href = '/';
    } else {
        document.getElementById('clientsList').innerText = 'Failed to load clients';
    }
}

function renderClients(clients){
    if(!clients || clients.length === 0){
        document.getElementById('clientsList').innerHTML = '<p style="color:#666">No clients found.</p>';
        return;
    }
    let html = '<table><thead><tr><th>ART Number</th><th>Name</th><th>Age</th><th>Address</th><th>Next Pickup</th><th>Status</th></tr></thead><tbody>';
    clients.forEach(c => {
        html += `<tr>
            <td>${c.artNumber || ''}</td>
            <td>${c.fullName || ''}</td>
            <td>${c.age || ''}</td>
            <td>${c.address || ''}</td>
            <td>${formatDate(c.nextPickup)}</td>
            <td>${c.status || ''}</td>
        </tr>`;
    });
    html += '</tbody></table>';
    document.getElementById('clientsList').innerHTML = html;
}

function formatDate(d){
    if(!d) return 'Not set';
    try{
        const dt = new Date(d);
        return dt.toLocaleDateString('en-GB');
    }catch(e){
        return d;
    }
}

function updateStats(clients){
    document.getElementById('totalClients').innerText = clients.length;
    const today = new Date().toISOString().split('T')[0];
    const dueToday = clients.filter(c => c.nextPickup === today).length;
    const overdue = clients.filter(c => c.nextPickup && (new Date(c.nextPickup) < new Date())).length;
    document.getElementById('dueToday').innerText = dueToday;
    document.getElementById('overdue').innerText = overdue;
}

document.getElementById('btnReload').addEventListener('click', fetchClients);
// initial load
fetchClients();
