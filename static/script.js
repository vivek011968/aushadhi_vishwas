// Generic variable to store user location globally once fetched
let currentLocation = "Unknown";

// Attempt to get user location
function fetchLocation(inputId = null) {
    if ("geolocation" in navigator) {
        navigator.geolocation.getCurrentPosition(function (position) {
            currentLocation = position.coords.latitude + "," + position.coords.longitude;
            if (inputId) {
                document.getElementById(inputId).value = currentLocation;
            }
        }, function (error) {
            console.error("Location access denied or unavailable.");
            if (inputId) {
                alert("Please enable location services or enter location manually.");
            }
        });
    } else {
        console.error("Geolocation not supported");
    }
}

// Ensure location is fetched upon loading
document.addEventListener("DOMContentLoaded", function() {
    fetchLocation();
    
    // Auto-init Scanner if the scanner container exists
    let readerElement = document.getElementById("reader");
    if (readerElement) {
        initScanner();
    }
    
    // Auto-init Map if the map container exists
    let mapElement = document.getElementById("fake-map");
    if (mapElement) {
        initMap();
    }
});

let html5QrcodeScanner;

function initScanner() {
    // Ultra-Robust Config for both Camera and File Scanner
    const config = { 
        fps: 30, 
        qrbox: (viewWidth, viewHeight) => {
            return { width: viewWidth * 0.85, height: viewHeight * 0.85 };
        },
        rememberLastUsedCamera: true,
        aspectRatio: 1.0,
        // Using the integer constant for QR_CODE (0) to ensure maximum compatibility
        formatsToSupport: [ 0 ] 
    };

    html5QrcodeScanner = new Html5QrcodeScanner("reader", config, false);
    html5QrcodeScanner.render(onScanSuccess, onScanFailure);

    // Apply visual enhancement to the video feed for better detection
    let observer = new MutationObserver(() => {
        const video = document.querySelector('#reader video');
        if (video) {
            video.style.filter = "contrast(1.2) brightness(1.1) saturate(1.1)";
            observer.disconnect();
        }
    });
    observer.observe(document.getElementById('reader'), { childList: true, subtree: true });
}


let isTorchOn = false;
function toggleTorch() {
    if (!html5QrcodeScanner) return;
    
    isTorchOn = !isTorchOn;
    html5QrcodeScanner.applyVideoConstraints({
        advanced: [{ torch: isTorchOn }]
    }).then(() => {
        const btn = document.getElementById('torch-btn');
        btn.innerHTML = isTorchOn ? 
            '<i class="fa-solid fa-bolt-slash"></i> Turn Flashlight Off' : 
            '<i class="fa-solid fa-bolt"></i> Turn Flashlight On';
        btn.className = isTorchOn ? 'btn btn-warning w-100' : 'btn btn-outline-warning w-100';
    }).catch(err => {
        console.error("Torch error:", err);
        showToast("Flashlight not supported on this device/browser.", "error");
    });
}

function onScanSuccess(decodedText, decodedResult) {
    // 1. INSTANTLY STOP THE SCANNER
    if (html5QrcodeScanner) {
        html5QrcodeScanner.clear().catch(e => console.log("Clear handled"));
    }

    // 2. Extract medicine_id from QR text or URL
    let medicine_id = decodedText;
    if (decodedText.includes('/verify/')) {
        let parts = decodedText.split('/verify/');
        medicine_id = parts[parts.length - 1];
    }

    // 3. Prepare parameters
    let scannerType = "Consumer";
    const scannerTypeInput = document.querySelector('input[name="scannerType"]:checked');
    if (scannerTypeInput) {
        scannerType = scannerTypeInput.value;
    }

    // 4. Show a quick Loading/Redirecting UI
    const readerDiv = document.getElementById("reader");
    if (readerDiv) {
        readerDiv.style.display = "none";
        const container = readerDiv.closest('.glass-card');
        if (container) {
            container.innerHTML = `
                <div class="text-center p-5">
                    <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;"></div>
                    <h4 class="mt-4 text-primary">Verifying Code...</h4>
                    <p class="text-muted small">Redirecting you to the full report instantly.</p>
                </div>
            `;
        }
    }

    // 5. IMMEDIATE REDIRECT (User requested: "open directly without checking anything")
    const redirectUrl = `/verify/${encodeURIComponent(medicine_id)}?location=${encodeURIComponent(currentLocation)}&scannerType=${encodeURIComponent(scannerType)}`;
    window.location.href = redirectUrl;
}

function onScanFailure(error) {
    // handle scan failure, usually better to ignore and keep scanning
}

function verifyMedicine(qrCodeData, scannerType, isDamaged = false) {
    let medicine_id = qrCodeData;
    if (qrCodeData.includes('/verify/')) {
        let parts = qrCodeData.split('/verify/');
        medicine_id = parts[parts.length - 1];
    }

    // Call our backend API for a preview first
    document.getElementById("result-title").innerText = "Analyzing...";
    document.getElementById("result-header").className = "text-center mb-4 text-info";
    
    let url = `/verify/${encodeURIComponent(medicine_id)}?format=json&location=${encodeURIComponent(currentLocation)}&scannerType=${encodeURIComponent(scannerType)}&isDamaged=${isDamaged}`;
    
    fetch(url)
    .then(response => response.json())
    .then(data => {
        // Store IDs for the redirect button
        data. medicine_id_raw = medicine_id;
        data.scannerType = scannerType;
        data.isDamaged = isDamaged;
        displayResult(data);
    })
    .catch((error) => {
        console.error('Error:', error);
        document.getElementById("result-title").innerText = "Connection Error";
    });
}

function displayResult(data) {
    const resultCard = document.getElementById("result-card");
    const resultTitleOuter = document.getElementById("result-header");
    const title = document.getElementById("result-title");
    const desc = document.getElementById("result-desc");
    const medDetails = document.getElementById("medicine-details");
    const supplyDetails = document.getElementById("supply-chain-details");
    const reportBtn = document.getElementById("report-btn");
    
    // Setup generic clears
    medDetails.style.display = "none";
    supplyDetails.style.display = "none";
    const externalView = document.getElementById("external-data-view");
    if (externalView) externalView.style.display = "none";
    
    reportBtn.style.display = "none";
    reportBtn.href = "/complaints"; // Reset default
    reportBtn.onclick = null; // Clear manual registration handler
    
    // Set UI depending on status
    let statusText = data.status || "Verification Result";
    let reasonText = data.reason || "Processed successfully.";
    
    if (statusText.includes("Verified")) {
        resultCard.className = "glass-card p-4 h-100 verified-box";
        resultTitleOuter.className = "text-center mb-4 text-success";
        title.innerHTML = '<i class="fa-solid fa-circle-check"></i> ' + statusText;
        
        if (data.medicine && data.medicine.is_external) {
            desc.innerHTML = `<span class="badge bg-success mb-2"><i class="fa-solid fa-shield-halved"></i> Global Trusted</span><br>Verified via: <strong>${data.medicine.trust_source}</strong>`;
        } else {
            desc.innerText = "This medicine has been cleared by Aushadhi Vishwas.";
        }
        
    } else if (statusText.includes("Expired") || statusText.includes("Suspicious")) {
        resultCard.className = "glass-card p-4 h-100 suspicious-box";
        resultTitleOuter.className = "text-center mb-4 text-warning";
        title.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> ' + statusText;
        desc.innerText = reasonText;
        reportBtn.innerText = "Raise a Problem";
        reportBtn.className = "btn btn-warning ms-2";
        if (data.medicine) {
            reportBtn.href = `/complaints?med_name=${encodeURIComponent(data.medicine.name)}&batch=${encodeURIComponent(data.medicine.batch_number)}`;
        }
        reportBtn.style.display = "inline-block";
        
    } else if (statusText === "Possible Fake Medicine" || statusText === "Fake") {
        resultCard.className = "glass-card p-4 h-100 fake-box";
        resultTitleOuter.className = "text-center mb-4 text-danger";
        title.innerHTML = '<i class="fa-solid fa-skull-crossbones"></i> ' + statusText;
        desc.innerText = reasonText || "This QR code does not exist in our trusted database.";
        reportBtn.innerText = "Report Counterfeit";
        reportBtn.className = "btn btn-danger ms-2";
        if (data.medicine) {
            reportBtn.href = `/complaints?med_name=${encodeURIComponent(data.medicine.name)}&batch=${encodeURIComponent(data.medicine.batch_number)}`;
        }
        reportBtn.style.display = "inline-block";
        
    } else if (statusText === "Unknown External QR Code") {
        resultCard.className = "glass-card p-4 h-100 suspicious-box";
        resultTitleOuter.className = "text-center mb-4 text-primary";
        title.innerHTML = '<i class="fa-solid fa-circle-question"></i> Unknown Product';
        desc.innerText = "This code is valid but not found in our trusted databases. You can register it if you trust the source.";
        reportBtn.innerText = "Register as Trusted";
        reportBtn.className = "btn btn-primary ms-2";
        reportBtn.onclick = registerAsTrusted;
        reportBtn.style.display = "inline-block";
    } else {
        resultCard.className = "glass-card p-4 h-100";
        resultTitleOuter.className = "text-center mb-4 text-muted";
        title.innerHTML = statusText;
        desc.innerText = reasonText;
    }

    // Populate Medicine fields and show the preview
    if (data.medicine) {
        document.getElementById("medicine-details").style.display = "block";
        document.getElementById("med-name").innerText = data.medicine.name || '--';
        document.getElementById("med-mfg").innerText = data.medicine.manufacturer || '--';
        document.getElementById("med-batch").innerText = data.medicine.batch_number || '--';
        document.getElementById("med-mfg-date").innerText = data.medicine.mfg_date || '--';
        document.getElementById("med-exp").innerText = data.medicine.exp_date || '--';
        document.getElementById("med-dist").innerText = data.medicine.distributor || '--';
        
        // Show "What's inside the QR" (Raw Content)
        if (data.medicine.raw_data) {
            const extView = document.getElementById("external-data-view");
            const rawContent = document.getElementById("raw-content");
            const extLinkBtn = document.getElementById("external-link-btn");
            
            if (extView) {
                extView.style.display = "block";
                rawContent.innerText = data.medicine.raw_data;
                
                // Show link button if it looks like a URL
                if (extLinkBtn) {
                    const content = data.medicine.raw_data;
                    if (content.startsWith("http://") || content.startsWith("https://")) {
                        extLinkBtn.href = content;
                        extLinkBtn.style.display = "inline-block";
                    } else {
                        extLinkBtn.style.display = "none";
                    }
                }
            }
        }

        // Add "View Full Report" button below the details
        const detailsContainer = document.getElementById("medicine-details");
        const existingViewBtn = document.getElementById("full-report-btn");
        if (existingViewBtn) existingViewBtn.remove();
        
        const viewBtn = document.createElement("a");
        viewBtn.id = "full-report-btn";
        viewBtn.className = "btn btn-success w-100 mt-3 btn-lg";
        viewBtn.href = `/verify/${encodeURIComponent(data.medicine_id_raw)}?location=${encodeURIComponent(currentLocation)}&scannerType=${encodeURIComponent(data.scannerType)}&isDamaged=${data.isDamaged}`;
        viewBtn.innerHTML = '<i class="fa-solid fa-arrow-right-long"></i> Proceed to Full Verification Report';
        detailsContainer.appendChild(viewBtn);
    }

    // Populate Supply Chain fields (if available in preview)
    if (data.supply_chain && data.supply_chain.length > 0) {
        const timeline = document.getElementById("supply-timeline");
        timeline.innerHTML = ""; // Clear existing
        data.supply_chain.forEach(log => {
            const li = document.createElement("li");
            li.innerHTML = `
                <strong>${log.stage}</strong> <br>
                <small class="text-muted"><i class="fa-solid fa-location-arrow"></i> ${log.location} &nbsp;|&nbsp; <i class="fa-solid fa-clock"></i> ${log.timestamp}</small>
            `;
            timeline.appendChild(li);
        });
        supplyDetails.style.display = "block";
    }
}

function resetScanner() {
    document.getElementById("result-view").style.display = "none";
    document.getElementById("reader").style.display = "block";
    initScanner();
}

// ----- Leaflet Map Implementation -----
function initMap() {
    var map = L.map('fake-map').setView([20.5937, 78.9629], 5); // Default to Center of India
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 19,
        attribution: '© OpenStreetMap Aushadhi Vishwas'
    }).addTo(map);

    // Fetch Fake Alerts Data
    fetch('/api/fake_alerts')
    .then(res => res.json())
    .then(data => {
        data.forEach(alertData => {
            const loc = alertData.location; // Should be lat,lng
            if (loc && loc !== "Unknown" && loc.includes(",")) {
                const parts = loc.split(",");
                const lat = parseFloat(parts[0]);
                const lng = parseFloat(parts[1]);
                
                if (!isNaN(lat) && !isNaN(lng)) {
                    var marker = L.circleMarker([lat, lng], {
                        color: 'red',
                        fillColor: '#f03',
                        fillOpacity: 0.5,
                        radius: 10
                    }).addTo(map);
                    
                    marker.bindPopup(`<b>Fake Alert Detected!</b><br>Reason: ${alertData.reason}<br>QR ID: ${alertData.qr_code_id}<br>Time: ${alertData.timestamp}`);
                }
            }
        });
    })
    .catch(err => console.error("Could not load map data", err));
}

function registerAsTrusted() {
    const qrId = document.getElementById("raw-content").innerText;
    if (!qrId || qrId === "--") {
        alert("No QR data found to register.");
        return;
    }

    if (confirm("Do you trust this medicine and want to register it as genuine in your local database?")) {
        fetch("/api/onboard_external", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                qr_code_id: qrId,
                name: "Manually Trusted Product",
                manufacturer: "External Manufacturer",
                batch_number: "External-Batch"
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                alert("Medicine registered successfully! It will now show as Verified.");
                location.reload();
            } else {
                alert("Error: " + data.message);
            }
        });
    }
}


function registerAsTrustedPage(qrId) {
    if (!qrId || qrId === "None" || qrId === "") {
        alert("No QR data found to register.");
        return;
    }

    if (confirm("Do you trust this medicine and want to register it as genuine in your local database?")) {
        fetch("/api/onboard_external", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                qr_code_id: qrId,
                name: "Manually Trusted Product",
                manufacturer: "External Manufacturer",
                batch_number: "External-Batch"
            })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                alert("Medicine registered successfully! It will now show as Verified.");
                location.reload();
            } else {
                alert("Error: " + data.message);
            }
        });
    }
}
