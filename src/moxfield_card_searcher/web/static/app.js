// Replace a broken Scryfall card image with a text placeholder.
// Used by elements that opt in via class="card-image-fallback" and a
// data-card-name attribute set to the alt text we'd otherwise lose.
document.addEventListener("error", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLImageElement)) return;
    if (!target.classList.contains("card-image-fallback")) return;
    const name = target.dataset.cardName ?? target.alt ?? "";
    const placeholder = document.createElement("div");
    placeholder.className = "card-placeholder";
    placeholder.textContent = name;
    target.replaceWith(placeholder);
}, true);
