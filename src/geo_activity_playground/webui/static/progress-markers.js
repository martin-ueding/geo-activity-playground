function makeProgressMarkerSvg(progress, small) {
    const clamped = Math.min(Math.max(progress ?? 0, 0), 1);
    const size = small ? 16 : 24;
    const cx = size / 2;
    const cy = size / 2;
    const r = small ? 5 : 8;
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
        <svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="#ffffff"/>
            ${fillMarkup}
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#111111" stroke-width="2"/>
        </svg>
    `;
}

function progressMarkerIcon(progress, isEighth) {
    const small = !!isEighth;
    const size = small ? 16 : 24;
    return L.divIcon({
        className: "",
        html: makeProgressMarkerSvg(progress, small),
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
    });
}

window.progressMarkerIcon = progressMarkerIcon;
