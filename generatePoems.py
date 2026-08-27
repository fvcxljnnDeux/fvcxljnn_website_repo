from pathlib import Path
import yaml
import markdown
import shutil
import re
import unicodedata
import html

def splitProperties(content):
    if not content.startswith("---"):
        return None, None

    parts = content.split("---", 2)

    if len(parts) < 3:
        return None, None

    properties = parts[1]
    markdownText = parts[2]

    try:
        metadata = yaml.safe_load(properties)
    except yaml.YAMLError:
        return None, None

    if not isinstance(metadata, dict):
        return None, None

    return metadata, markdownText

def isValidPoem(metadata, markdownText):
    requiredProperties = [
        "aliases",
        "Verfasst:",
        "Sprache:",
        "Form:",
        "Poem-Index:",
        "Davor:",
        "Danach:",
        "Letzte Revision:",
        "Kategorien (Inhalt):",
        "Kategorien (Meta):",
        "Notes:"
    ]

    for property in requiredProperties:
        if property not in metadata:
            return False

    aliases = metadata.get("aliases")

    if not aliases:
        return False

    lines = markdownText.splitlines()

    firstHeading = None
    firstHeadingIndex = None

    for i, line in enumerate(lines):
        if line.startswith("# "):
            firstHeading = line[2:].strip()
            firstHeadingIndex = i
            break

    if firstHeading is None:
        return False

    reservedHeadings = [
        "Version Control",
        "Behind the Scenes",
        "Anmerkungen",
        "Referenzen"
    ]

    if firstHeading in reservedHeadings:
        return False

    for line in lines[firstHeadingIndex + 1:]:
        if line.startswith("# "):
            break

        if line.strip():
            return True

    return False

def cleanListFormat(values):
    if values is None:
        return []

    cleanValues = []

    for value in values:
        if isinstance(value, str):
            value = value.removeprefix("[[").removesuffix("]]")

        cleanValues.append(value)

    return cleanValues

def normalizeMetadata(metadata):
    normalized = {
        "title": None,
        "date": None,
        "languages": [],
        "forms": [],
        "index": None,
        "lastRevision": None,
        "categoriesContent": [],
        "categoriesMeta": [],
        "notes": []
    }

    aliases = metadata.get("aliases")
    if aliases:
        normalized["title"] = aliases[0]

    normalized["date"] = metadata.get("Verfasst:")
    normalized["languages"] = cleanListFormat(metadata.get("Sprache:"))
    normalized["forms"] = cleanListFormat(metadata.get("Form:"))
    normalized["index"] = metadata.get("Poem-Index:")
    normalized["lastRevision"] = metadata.get("Letzte Revision:")
    normalized["categoriesContent"] = cleanListFormat(metadata.get("Kategorien (Inhalt):"))
    normalized["categoriesMeta"] = cleanListFormat(metadata.get("Kategorien (Meta):"))
    normalized["notes"] = cleanListFormat(metadata.get("Notes:"))

    return normalized

def splitSections(markdownSections):
    sections = {
        "poem": "",
        "versionControl": "",
        "behindTheScenes": "",
        "comment": "",
        "references": ""
    }

    currentSection = "poem"
    poemTitleFound = False

    for line in markdownSections.splitlines():
        if line.startswith("# "):
            heading = line[2:].strip()

            if not poemTitleFound:
                poemTitleFound = True
                continue

            if heading == "Version Control":
                currentSection = "versionControl"
                continue

            if heading == "Behind the Scenes":
                currentSection = "behindTheScenes"
                continue

            if heading == "Anmerkungen":
                currentSection = "comment"
                continue

            if heading == "Referenzen":
                currentSection = "references"
                continue

        sections[currentSection] += line + "\n"

    for key in sections:
        sections[key] = sections[key].strip()

    return sections

def splitVersionControl(versionControl):
    versions = []
    currentVersion = None

    for line in versionControl.splitlines():
        if line.startswith("## "):
            versionTitle = line[3:].strip()

            currentVersion = {
                "title": versionTitle,
                "text": ""
            }

            versions.append(currentVersion)
            continue

        if currentVersion is not None:
            currentVersion["text"] += line + "\n"

    for version in versions:
        version["text"] = version["text"].strip()

    return versions

def splitReferences(references):
    referenceItems = re.split(r"\n\s*\n", references.strip())

    return referenceItems

def convertObsidianLinks(text, poemsBySourceStem):
    pattern = r"\[\[([^\[|]+)(?:\|([^\]]+))?\]\]"

    def replaceLink(match):
        target = match.group(1)
        displayText = match.group(2) or target

        safeDisplayText = html.escape(displayText)

        linkedPoem = poemsBySourceStem.get(target)

        if linkedPoem is None:
            return safeDisplayText

        return (f'<a href="{linkedPoem["fileName"]}.html">{safeDisplayText}</a>')

    return re.sub(pattern, replaceLink, text)

def getAlternateSpelling(poemFile):
    stem = poemFile.stem

    parts = stem.split(" – ", 1)

    if len(parts) == 2:
        return parts[1]

    return stem

def createSlug(alternateSpelling):
    slug = alternateSpelling.lower()

    slug = slug.replace("ä", "ae")
    slug = slug.replace("ö", "oe")
    slug = slug.replace("ü", "ue")
    slug = slug.replace("ß", "ss")

    slug = slug.replace("'", "").replace("’", "")

    slug = unicodedata.normalize("NFKD", slug)
    slug = slug.encode("ascii", "ignore").decode("ascii")

    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")

    return slug

def getPoemFileName(index, slug):
    if index is not None:
        return str(index)

    return slug

def getPoemDate(date, poemFile):
    if date is not None:
        return date.strftime("%Y-%m-%d")

    fileDate = poemFile.stem[:10]

    return fileDate

def buildDateHTML(dateString):
    year, month, day = dateString.split("-")

    formattedYear = "????" if year == "0000" else year
    formattedMonth = "??" if month == "00" else month
    formattedDay = "??" if day == "00" else day

    formattedDate = (f"{formattedDay}/{formattedMonth}/{formattedYear}")

    dateIsComplete = (
        year != "0000"
        and month != "00"
        and day != "00"
    )

    if dateIsComplete:
        return (f'<time class="poem-date" datetime="{dateString}">{formattedDate}</time>')

    return (f'<span class="poem-date date-uncertain">{formattedDate}</span>')

def buildPoem(metadata, sections, poemFile):
    alternateSpelling = getAlternateSpelling(poemFile)
    slug = createSlug(alternateSpelling)
    fileName = getPoemFileName(metadata["index"], slug)

    poem = {
        "title": metadata["title"],
        "alternateSpelling": alternateSpelling,
        "slug": slug,
        "sourceStem": poemFile.stem,
        "fileName": fileName,
        "date": metadata["date"],
        "dateString": getPoemDate(metadata["date"], poemFile),
        "languages": metadata["languages"],
        "forms": metadata["forms"],
        "index": metadata["index"],
        "lastRevision": metadata["lastRevision"],
        "categoriesContent": metadata["categoriesContent"],
        "categoriesMeta": metadata["categoriesMeta"],
        "notes": metadata["notes"],
        "poemText": sections["poem"],
        "versionControl": splitVersionControl(sections["versionControl"]),
        "comment": sections["comment"],
        "references": sections["references"],
        "images": []
    }

    return poem

def getImageKey(imageFile):
    stem = imageFile.stem

    if "_&&_" in stem:
        key, imageNumber = stem.rsplit("_&&_", 1)

        if imageNumber.isdigit():
            stem = key

    if stem.isdigit():
        return int(stem)

    return stem

def addImageToDictionary(dictionary, key, imageFile):
    if key not in dictionary:
        dictionary[key] = []

    dictionary[key].append(imageFile)

def getImageNumber(imageFile):
    stem = imageFile.stem

    if "_&&_" not in stem:
        return 0

    _, imageNumber = stem.rsplit("_&&_", 1)

    if not imageNumber.isdigit():
        raise ValueError(f"Ungültige Bildnummer: {imageFile.name}")

    return int(imageNumber)

def assignImages(poem, imagesByKey):
    if poem["index"] is not None:
        key = poem["index"]
    else:
        key = poem["alternateSpelling"]

    images = imagesByKey.get(key, [])

    poem["images"] = sorted(images, key=getImageNumber)

def buildPoemPage(poem, poemsBySourceStem, previousPoem=None, nextPoem=None):
    safeTitle = html.escape(poem["title"])

    poemHTML = markdown.markdown(poem["poemText"], extensions=["nl2br"])

    indexHTML = ""

    if poem["index"] is not None:
        indexHTML = f'<span class="poem-index">[{poem["index"]}]</span>'

    dateHTML = buildDateHTML(poem["dateString"])

    lastRevisionHTML = ""

    if poem["lastRevision"] is not None:
        revisionDate = poem["lastRevision"].strftime("%d/%m/%Y")
        revisionDateMachineFriendly = poem["lastRevision"].isoformat()

        lastRevisionHTML = (
            f'<span class="poem-last-revision">'
            f'Letzte Revision: <time datetime="{revisionDateMachineFriendly}">{revisionDate}</time>'
            f'</span>'
        )

    imagesHTML = ""
    imagesSectionHTML = ""

    if poem["images"]:
        for image in poem["images"]:
            imagesHTML += f"""<img class="poem-image" src="../../assets/poem_images/{image.name}" alt="Bild zum Gedicht">"""

        imagesSectionHTML = f"""<div class="poem-images">
            {imagesHTML}
        </div>"""

    versionControlHTML = ""

    if poem["versionControl"]:
        versionsHTML = ""

        for version in poem["versionControl"]:
            safeVersionTitle = html.escape(version["title"])

            versionTextHTML = markdown.markdown(version["text"], extensions=["nl2br"])

            versionsHTML += f"""<details class="version-entry">
                <summary class="version-title">{safeVersionTitle}</summary>
                <article class="version-text">
                    {versionTextHTML}
                </article>
            </details>"""

        versionControlHTML = f"""<section class="poem-version-control">
            <h2>Version Control</h2>
            {versionsHTML}
        </section>"""

    commentHTML = ""

    if poem["comment"]:
        commentContent = markdown.markdown(poem["comment"], extensions=["nl2br"])

        commentHTML = f"""<section class="poem-comment">
            <h2>Anmerkungen</h2>
            {commentContent}
        </section>"""

    referencesHTML = ""

    if poem["references"]:
        referenceItemsHTML = ""

        for reference in splitReferences(poem["references"]):
            reference = convertObsidianLinks(reference, poemsBySourceStem)
            referenceHTML = markdown.markdown(reference, extensions=["nl2br"])

            referenceItemsHTML += f"""<li class="reference-entry">{referenceHTML}</li>"""

        referencesHTML = f"""<section class="poem-references">
            <h2>Referenzen</h2>
            <ul class="reference-list">
                {referenceItemsHTML}
            </ul>
        </section>"""

    previousHTML = ""
    nextHTML = ""

    if previousPoem is not None:
        safePreviousTitle = html.escape(previousPoem["title"])

        previousHTML = (
            f'<a class="poem-nav-previous" '
            f'href="{previousPoem["fileName"]}.html">'
            f'← {safePreviousTitle}</a>'
        )

    if nextPoem is not None:
        safeNextTitle = html.escape(nextPoem["title"])

        nextHTML = (
            f'<a class="poem-nav-next" '
            f'href="{nextPoem["fileName"]}.html">'
            f'{safeNextTitle} →</a>'
        )

    htmlPage = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>{safeTitle}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="32x32" href="../../assets/grafiken/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="../../assets/grafiken/favicon-16x16.png">
    <link rel="shortcut icon" href="../../assets/grafiken/favicon.ico" type="image/x-icon">
    <link rel="apple-touch-icon" sizes="180x180" href="../../assets/grafiken/favicon_apple-touch-icon-180x180.png">
    <link rel="icon" href="../../assets/grafiken/logo.svg" type="image/svg+xml" sizes="any">
    <link rel="stylesheet" type="text/css" href="../../style.css">
</head>

<body>
    <header>
        <nav>
            <a href="../../index.html">Startseite</a>
            <a href="../gallery.html">Galerie</a>
            {previousHTML}
            {nextHTML}
        </nav>
    </header>

    <main class="site-main">
        <article class="poem-page">
            <header class="poem-header">
                <h1 class="poem-title">{safeTitle}</h1>
                {indexHTML}
                {dateHTML}
            </header>

            <div class="poem-content">
                {poemHTML}
            </div>

            {lastRevisionHTML}

            {imagesSectionHTML}
        </article>

        {versionControlHTML}

        {commentHTML}

        {referencesHTML}

        <nav class="poem-navigation">
            {previousHTML}
            {nextHTML}
        </nav>
    </main>
</body>
</html>"""

    return htmlPage

def buildPoemsIndexPage(introductionMarkdown):
    lines = introductionMarkdown.splitlines()
    
    title = None
    contentLines = []
    
    for line in lines:
        if title is None and line.startswith("# "):
            title = line[2:].strip()
            continue
    
        if title is not None:
            contentLines.append(line)
    
    content = "\n".join(contentLines).strip()

    safeTitle = html.escape(title)
    contentHTML = markdown.markdown(content, extensions=["nl2br"])

    htmlPage = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Poems</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="32x32" href="../assets/grafiken/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="../assets/grafiken/favicon-16x16.png">
    <link rel="shortcut icon" href="../assets/grafiken/favicon.ico" type="image/x-icon">
    <link rel="apple-touch-icon" sizes="180x180" href="../assets/grafiken/favicon_apple-touch-icon-180x180.png">
    <link rel="icon" href="../assets/grafiken/logo.svg" type="image/svg+xml" sizes="any">
    <link rel="stylesheet" type="text/css" href="../style.css">
</head>

<body>
    <header>
        <nav>
            <a href="../index.html">Startseite</a>
        </nav>
    </header>
    
    <main class="site-main">
        <section class="poems-introduction">
            <h1>{safeTitle}</h1>
            
            <div class="poems-introduction-text">
                {contentHTML}
            </div>
        </section>
        
        <nav class="poems-navigation">
            <a href="gallery.html">Galerie</a>
            <a href="inspirations.html">Inspirationen</a>
        </nav>
    </main>
</body>
</html>"""

    return htmlPage

def buildPoemsGalleryPage(poems):
    poemLinks = ""

    for poem in poems:
        safeTitle = html.escape(poem["title"])

        poemLinks += (
            f'<li>'
            f'<a href="works/{poem["fileName"]}.html">{safeTitle}</a>'
            f'</li>\n'
        )

    htmlPage = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>Galerie</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="32x32" href="../assets/grafiken/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="../assets/grafiken/favicon-16x16.png">
    <link rel="shortcut icon" href="../assets/grafiken/favicon.ico" type="image/x-icon">
    <link rel="apple-touch-icon" sizes="180x180" href="../assets/grafiken/favicon_apple-touch-icon-180x180.png">
    <link rel="icon" href="../assets/grafiken/logo.svg" type="image/svg+xml" sizes="any">
    <link rel="stylesheet" type="text/css" href="../style.css">
</head>

<body>
    <main>
        <h1>Galerie</h1>
        <ul>
            {poemLinks}
        </ul>
    </main>
</body>
</html>"""

    return htmlPage

def parseInspirations(inspirationsMarkdown):
    inspirations = {
        "title": None,
        "artists": []
    }

    pageTitleFound = False
    currentArtist = None
    currentWork = None
    currentSection = None

    for line in inspirationsMarkdown.splitlines():
        if line.startswith("# "):
            heading = line[2:].strip()

            if not pageTitleFound:
                inspirations["title"] = heading
                pageTitleFound = True
                continue

            currentArtist = {
                "name": heading,
                "works": []
            }

            inspirations["artists"].append(currentArtist)
            
            currentWork = None
            currentSection = None
            continue

        if line.startswith("## "):
            if currentArtist is None:
                continue

            currentWork = {
                "title": line[3:].strip(),
                "links": "",
                "comment": ""
            }

            currentArtist["works"].append(currentWork)

            currentSection = None
            continue

        if line.startswith("### "):
            if currentWork is None:
                continue

            heading = line[4:].strip()

            if heading == "Links:":
                currentSection = "links"
            elif heading == "Anmerkungen:":
                currentSection = "comment"
            else:
                currentSection = None

            continue

        if currentWork is not None and currentSection is not None:
            currentWork[currentSection] += line + "\n"

    for artist in inspirations["artists"]:
        for work in artist["works"]:
            work["links"] = work["links"].strip()
            work["comment"] = work["comment"].strip()

    return inspirations

def buildPoemsInspirationsPage(inspirations):
    safeTitle = html.escape(inspirations["title"])

    artistsHTML = ""

    for artist in inspirations["artists"]:
        safeArtistName = html.escape(artist["name"])

        worksHTML = ""

        for work in artist["works"]:
            safeWorkTitle = html.escape(work["title"])

            linksHTML = ""
            commentHTML = ""

            if work["links"]:
                linksHTML = markdown.markdown(work["links"])

            if work["comment"]:
                commentHTML = markdown.markdown(work["comment"], extensions=["nl2br"])

            if work["links"] or work["comment"]:
                worksHTML += f"""<details class="inspirations-work">
                    <summary class="inspirations-work-title">
                        {safeWorkTitle}
                    </summary>
                    
                    <div class="inspirations-links">
                        {linksHTML}
                    </div>

                    <div class="inspirations-comment">
                        {commentHTML}
                    </div>
                </details>"""
            else:
                worksHTML += f"""<p class="inspirations-work-title">
                    {safeWorkTitle}
                </p>"""

        artistsHTML += f"""<section class="inspirations-artist">
            <h2>{safeArtistName}</h2>
            
            {worksHTML}
        </section>"""

    htmlPage = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <title>{safeTitle}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" type="image/png" sizes="32x32" href="../assets/grafiken/favicon-32x32.png">
    <link rel="icon" type="image/png" sizes="16x16" href="../assets/grafiken/favicon-16x16.png">
    <link rel="shortcut icon" href="../assets/grafiken/favicon.ico" type="image/x-icon">
    <link rel="apple-touch-icon" sizes="180x180" href="../assets/grafiken/favicon_apple-touch-icon-180x180.png">
    <link rel="icon" href="../assets/grafiken/logo.svg" type="image/svg+xml" sizes="any">
    <link rel="stylesheet" type="text/css" href="../style.css">
</head>

<body>
    <header>
        <nav>
            <a href="../index.html">Startseite</a>
            <a href="index.html">Poems</a>
        </nav>
    </header>
    
    <main class="site-main">
        <h1>{safeTitle}</h1>
        
        {artistsHTML}
    </main>
</body>
</html>"""

    return htmlPage

poemSourceDirectory = Path(r"D:\Obsidian\Drip Vault\(2) Poems")
imageSourceDirectory = Path(r"C:\Users\fvcxljnn\iCloudDrive\Daily Poem Snaps")

poemsIntroductionSource = poemSourceDirectory / "Introduction.md"
poemsInspirationsSource = poemSourceDirectory / "Inspirations.md"

websiteDirectory = Path(r"B:\fvcxljnn_website\fvcxljnn_website_repo")

poemsDirectory = websiteDirectory / "poems"
worksDirectory = poemsDirectory / "works"
worksDirectory.mkdir(parents=True, exist_ok=True)

poemsIndexFile = poemsDirectory / "index.html"
poemsDailyPoemsFile = poemsDirectory / "daily-poems.html"
poemsGalleryFile = poemsDirectory / "gallery.html"
poemsInspirationsFile = poemsDirectory / "inspirations.html"

websiteImageDirectory = websiteDirectory / "assets" / "poem_images"
websiteImageDirectory.mkdir(parents=True, exist_ok=True)

numberedPoemSourceDirectories = [
    directory
    for directory in poemSourceDirectory.iterdir()
    if directory.is_dir()
    and re.match(r"^\d{2} - ", directory.name)
]

poemFiles = []

for directory in numberedPoemSourceDirectories:
    poemFiles.extend(directory.rglob("*.md"))

imageFiles = [
    file
    for file in imageSourceDirectory.rglob("*")
    if file.is_file() and file.suffix.lower() == ".jpg"
]

allPoems = []
visiblePoems = []
hiddenPoems = []
invalidFiles = []

poemsBySourceStem = {}
imagesByKey = {}

for imageFile in imageFiles:
    key = getImageKey(imageFile)
    addImageToDictionary(imagesByKey, key, imageFile)

for poemFile in poemFiles:
    content = poemFile.read_text(encoding="utf-8")

    metadata, markdownText = splitProperties(content)

    if metadata is None:
        invalidFiles.append(poemFile)
        continue

    if not isValidPoem(metadata, markdownText):
        invalidFiles.append(poemFile)
        continue

    normalizedMetadata = normalizeMetadata(metadata)
    markdownSections = splitSections(markdownText)

    poem = buildPoem(normalizedMetadata, markdownSections, poemFile)
    allPoems.append(poem)

for poem in allPoems:
    if "hidden" in poem["notes"]:
        hiddenPoems.append(poem)
        continue

    visiblePoems.append(poem)

for poem in visiblePoems:
    poemsBySourceStem[poem["sourceStem"]] = poem
    assignImages(poem, imagesByKey)

    for image in poem["images"]:
        targetFile = websiteImageDirectory / image.name
        shutil.copy2(image, targetFile)

for i, poem in enumerate(visiblePoems):
    previousPoem = None
    nextPoem = None

    if i > 0:
        previousPoem = visiblePoems[i - 1]

    if i < len(visiblePoems) - 1:
        nextPoem = visiblePoems[i + 1]

    htmlPage = buildPoemPage(poem, poemsBySourceStem, previousPoem, nextPoem)

    outputFile = worksDirectory / f'{poem["fileName"]}.html'

    outputFile.write_text(htmlPage, encoding="utf-8")

poemsIntroductionMarkdown = poemsIntroductionSource.read_text(encoding="utf-8")

poemsIndexHTML = buildPoemsIndexPage(poemsIntroductionMarkdown)
poemsIndexFile.write_text(poemsIndexHTML, encoding="utf-8")

poemsGalleryHTML = buildPoemsGalleryPage(visiblePoems)
poemsGalleryFile.write_text(poemsGalleryHTML, encoding="utf-8")

poemsInspirationsMarkdown = poemsInspirationsSource.read_text(encoding="utf-8")
poemsInspirationsData = parseInspirations(poemsInspirationsMarkdown)

poemsInspirationsHTML = buildPoemsInspirationsPage(poemsInspirationsData)
poemsInspirationsFile.write_text(poemsInspirationsHTML, encoding="utf-8")

print("=== GENERIERUNG ABGESCHLOSSEN ===")
print()
print(f"Verarbeitete Poems: {len(visiblePoems)}")
print(f"Hidden Poems: {len(hiddenPoems)}")
print(f"Ungültige Dateien: {len(invalidFiles)}")
if invalidFiles:
    print()
    print("Ungültig:")
    print()
    for file in invalidFiles:
        print(file.stem)
print()