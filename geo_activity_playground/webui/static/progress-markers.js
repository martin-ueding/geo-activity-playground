function makeProgressMarkerSvg(progress) {
    const clamped = Math.min(Math.max(progress ?? 0, 0), 1);
    const cx = 12;
    const cy = 12;
    const r = 8;
    const fillColor = "#00aaff";
    let fillMarkup = "";
    if (clamped >= 1) {
        fillMarkup = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fillColor}"/>`;
    } else if (clamped > 0) {
        const angle = -Math.PI / 2 + clamped * 2 * Math.PI;
        const endX = cx + r * Math.cos(angle);
        const endY = cy + r * Math.sin(angle);
        const largeArc = clamped > 0.5 ? 1 : 0;
        fillMarkup =
            `<path d="M ${cx} ${cy} L ${cx} ${cy - r} A ${r} ${r} 0 ${largeArc} 1 ${endX} ${endY} Z" fill="${fillColor}"/>`;
    }
    return `
        <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="#ffffff"/>
            ${fillMarkup}
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#111111" stroke-width="2"/>
        </svg>
    `;
}

function progressMarkerIcon(progress) {
    return L.divIcon({
        className: "",
        html: makeProgressMarkerSvg(progress),
        iconSize: [24, 24],
        iconAnchor: [12, 12]
    });
}

window.progressMarkerIcon = progressMarkerIcon;
