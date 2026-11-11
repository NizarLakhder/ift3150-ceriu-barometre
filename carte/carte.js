// Carte du baromètre PGA-Eau. Les données viennent de donnees.js, produit par exporter_carte.py.

// Du plus foncé au plus pâle : plus la trace est forte, plus la couleur l'est.
const COULEURS = { pga: "#1f4e79", liee: "#8db7dc", outil: "#d2e3f1", aucune: "#f2f1ec" };

const ETATS = {
  pga: "PGA-Eau repéré dans le SEAO",
  liee: "Démarche liée repérée dans le SEAO",
  outil: "Outil de gestion des actifs seulement",
  aucune: "Aucune trace dans les exports lus",
};

// Les classements de demarches.csv, dits en mots simples.
const CLASSEMENTS = {
  elaboration: "Préparation du PGA-Eau",
  etape: "Étape du PGA-Eau",
  plan_intervention: "Plan d'intervention",
  plan_gestion_actifs: "Plan de gestion des actifs",
  demarche_voisine: "Démarche voisine",
  outil: "Logiciel ou outil de gestion des actifs",
};

const MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
              "septembre", "octobre", "novembre", "décembre"];

const montants = new Intl.NumberFormat("fr-CA", { style: "currency", currency: "CAD" });
const nombres = new Intl.NumberFormat("fr-CA");

// « 2025-09-08 » devient « 8 septembre 2025 », et le premier du mois « 1er ».
function dateEnMots(texte) {
  const [annee, mois, jour] = texte.split("-").map(Number);
  return `${jour === 1 ? "1er" : jour} ${MOIS[mois - 1]} ${annee}`;
}

// « du 1er au 31 mai 2026 », « du 1er août au 18 octobre 2026 » : sans répéter le mois ni l'année.
function periodeEnMots(debut, fin) {
  const [a1, m1] = debut.split("-").map(Number);
  const [a2, m2] = fin.split("-").map(Number);
  let premier = dateEnMots(debut);
  if (a1 === a2) premier = premier.replace(` ${a1}`, "");
  if (a1 === a2 && m1 === m2) premier = premier.replace(` ${MOIS[m1 - 1]}`, "");
  return `du ${premier} au ${dateEnMots(fin)}`;
}

function echapper(texte) {
  return String(texte).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

// Ce qu'on sait du mandat, en une phrase.
function phraseMandat(d) {
  if (d.etat === "mandat_attribue") {
    let phrase = d.date_attribution ? `Mandat attribué le ${dateEnMots(d.date_attribution)}` : "Mandat attribué";
    if (d.fournisseur) phrase += ` à ${echapper(d.fournisseur)}`;
    if (d.montant !== null) phrase += `, pour ${montants.format(d.montant)}`;
    return phrase + ".";
  }
  if (d.etat === "appel_offres_en_cours") {
    return `Appel d'offres publié le ${dateEnMots(d.date_publication)}, sans attribution dans les exports lus.`;
  }
  if (d.etat === "appel_offres_annule") {
    return `Appel d'offres publié le ${dateEnMots(d.date_publication)}, puis annulé.`;
  }
  if (d.etat === "plan_adopte") return "Plan adopté.";
  if (d.etat === "plan_publie") return "Plan publié.";
  return "";
}

function htmlDemarche(d) {
  let html = `<div class="demarche"><p><strong>${CLASSEMENTS[d.classement] || echapper(d.classement)}</strong></p>`;
  html += `<p>${phraseMandat(d)}</p>`;
  if (d.notes) html += `<p class="note">${echapper(d.notes)}</p>`;
  if (d.lien) html += `<p><a href="${echapper(d.lien)}" target="_blank" rel="noopener">Voir l'avis sur le SEAO</a></p>`;
  return html + "</div>";
}

function htmlFiche(p) {
  let html = `<div class="fiche"><h2>${echapper(p.nom)}</h2>`;
  html += `<p>${echapper(p.designation)}, ${echapper(p.region)}`;
  if (p.mrc) html += `<br>${echapper(p.genre_mrc || "MRC")} : ${echapper(p.mrc)}`;
  html += "</p>";
  if (p.population !== null) {
    html += `<p>${nombres.format(p.population)} ${p.population > 1 ? "habitants" : "habitant"}</p>`;
  }
  html += `<p class="etat">${ETATS[p.etat]}</p>`;
  if (p.etat === "aucune") {
    html += "<p>Ça ne veut pas dire que la municipalité n'a pas de plan : le mandat peut ne pas passer par le SEAO.</p>";
  }
  if (p.etat === "outil") {
    html += "<p>Un logiciel aide à gérer les actifs, mais ce n'est pas une démarche de plan.</p>";
  }
  html += p.demarches.map(htmlDemarche).join("");
  if (p.site) {
    html += `<p class="demarche"><a href="${echapper(p.site)}" target="_blank" rel="noopener">Site web de la municipalité</a></p>`;
  }
  return html + "</div>";
}

// --- La carte ---

// Au départ, le sud du Québec, où sont presque toutes les traces. Sur un petit
// écran, il faut un cran de zoom de moins.
const grandEcran = document.getElementById("carte").clientWidth > 1000;
const carte = L.map("carte", { preferCanvas: true, minZoom: 4, maxZoom: 13 })
  .setView([48.3, -72.3], grandEcran ? 7 : 6);

// Fond OpenStreetMap, gratuit et sans clé. Il est passé en gris dans carte.css
// pour que les couleurs du baromètre ressortent.
const attribution = '&copy; les contributeurs d\'<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>, '
  + "découpages administratifs du MRNF";
L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution, maxZoom: 19 }).addTo(carte);

function style(etat) {
  return { color: "#8f8a80", weight: 0.6, fillColor: COULEURS[etat], fillOpacity: etat === "aucune" ? 0.35 : 0.9 };
}
const SOULIGNE = { weight: 2.5, color: "#222" };

// Les municipalités coloriées sont dessinées en dernier, pour que leur bord reste visible.
const ordre = { aucune: 0, outil: 1, liee: 2, pga: 3 };
const territoires = [...DONNEES.territoires.features].sort((a, b) => ordre[a.properties.etat] - ordre[b.properties.etat]);

const parCode = new Map();
let choisie = null;

L.geoJSON({ type: "FeatureCollection", features: territoires }, {
  style: (f) => style(f.properties.etat),
  onEachFeature: (f, couche) => {
    parCode.set(f.properties.code, couche);
    couche.bindTooltip(f.properties.nom, { sticky: true, direction: "top" });
    couche.bindPopup(() => htmlFiche(f.properties), { maxWidth: 340, maxHeight: 420 });
    couche.on("click", () => marquer(f.properties.code));
    couche.on("mouseover", () => couche.setStyle({ weight: 2, color: "#444" }));
    couche.on("mouseout", () => couche.setStyle(couche === choisie ? SOULIGNE : style(f.properties.etat)));
  },
}).addTo(carte);

// Souligne la municipalité choisie et met son code dans l'adresse de la page,
// pour qu'on puisse envoyer le lien.
function marquer(code) {
  if (choisie) choisie.setStyle(style(choisie.feature.properties.etat));
  choisie = parCode.get(code);
  choisie.setStyle(SOULIGNE);
  history.replaceState(null, "", `#${code}`);
}

function montrer(code) {
  const couche = parCode.get(code);
  if (!couche) return;
  carte.fitBounds(couche.getBounds(), { maxZoom: 10, padding: [40, 40] });
  marquer(code);
  couche.openPopup(couche.getBounds().getCenter());
}

// --- Le panneau de gauche ---

const proprietes = DONNEES.territoires.features.map((f) => f.properties);
const parEtiquette = new Map(proprietes.map((p) => [p.etiquette, p.code]));

document.getElementById("date-donnees").textContent = dateEnMots(DONNEES.genere_le);
for (const etat of ["pga", "liee", "outil", "aucune"]) {
  const nombre = proprietes.filter((p) => p.etat === etat).length;
  document.getElementById(`nb-${etat}`).textContent = nombres.format(nombre);
}

for (const etat of ["pga", "liee", "outil"]) {
  const liste = document.getElementById(`liste-${etat}`);
  for (const p of proprietes.filter((q) => q.etat === etat).sort((a, b) => a.nom.localeCompare(b.nom, "fr"))) {
    const element = document.createElement("li");
    const bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "lien";
    bouton.textContent = p.nom;
    bouton.addEventListener("click", () => montrer(p.code));
    element.appendChild(bouton);
    liste.appendChild(element);
  }
}

// Recherche : la liste propose les noms; on accepte aussi un nom tapé sans accents.
const noms = document.getElementById("noms");
for (const etiquette of [...parEtiquette.keys()].sort((a, b) => a.localeCompare(b, "fr"))) {
  const option = document.createElement("option");
  option.value = etiquette;
  noms.appendChild(option);
}

const sansAccents = (texte) => texte.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
const recherche = document.getElementById("recherche");
const message = document.getElementById("message-recherche");

function chercher() {
  const texte = recherche.value;
  message.hidden = true;
  if (!texte.trim()) return;
  if (parEtiquette.has(texte)) {
    montrer(parEtiquette.get(texte));
    return;
  }
  const cherche = sansAccents(texte);
  const trouvees = proprietes.filter((p) => sansAccents(p.nom) === cherche);
  if (trouvees.length === 1) {
    montrer(trouvees[0].code);
  } else {
    message.textContent = trouvees.length > 1
      ? "Plusieurs municipalités portent ce nom : choisissez-la dans la liste."
      : "Aucune municipalité de ce nom. Choisissez-la dans la liste.";
    message.hidden = false;
  }
}

recherche.addEventListener("change", chercher);
recherche.addEventListener("keydown", (e) => { if (e.key === "Enter") chercher(); });

// --- La fenêtre « À propos » ---

document.getElementById("periodes").textContent = DONNEES.periodes
  .map((p) => periodeEnMots(p.debut, p.fin)).join(", puis ");
document.getElementById("version-contours").textContent = DONNEES.version_contours || "inconnue";
const minuscule = (texte) => texte.charAt(0).toLowerCase() + texte.slice(1);
document.getElementById("hors-carte").textContent = DONNEES.hors_carte.length
  ? DONNEES.hors_carte.map((d) => `${d.organisme} (${minuscule(CLASSEMENTS[d.classement] || d.classement)})`).join(", ")
  : "aucune pour l'instant";

const aPropos = document.getElementById("a-propos");
document.getElementById("ouvrir-a-propos").addEventListener("click", () => aPropos.showModal());

// Une adresse comme carte/index.html#97007 ouvre directement la fiche de Sept-Îles.
const codeDansAdresse = location.hash.slice(1);
if (parCode.has(codeDansAdresse)) montrer(codeDansAdresse);
