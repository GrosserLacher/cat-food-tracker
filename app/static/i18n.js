/*
  i18n.js – Übersetzungen für den Cat Food Tracker
  Ablage: app/static/i18n.js   (wird von index.html geladen)

  So funktioniert es
  ------------------
  Die Oberfläche ist auf Deutsch geschrieben. Jeder deutsche Text, der hier als Schlüssel
  (links) steht, wird in der gewählten Sprache durch den Eintrag rechts ersetzt.
  Texte ohne Eintrag bleiben deutsch. Namen aus deinen Daten (Tiere, Hersteller, Sorten)
  werden nicht übersetzt.

  Weitere Sprache hinzufügen
  --------------------------
  1. Den Block "en" kopieren, z. B. als "fr", und die rechte Seite übersetzen.
  2. Unter "languages" und "locale" eintragen: fr: 'Français' bzw. fr: 'fr-FR'.
  3. Optional unter "rx" einen Block "fr" für Sätze mit wechselnden Teilen anlegen.
  Die Sprachwahl erscheint dann automatisch im Kopf der App und unter Einstellungen → Design.

  Deutsche Texte ändern
  ---------------------
  Im Block "de" kannst du deutsche Formulierungen überschreiben, z. B.  'Füttern': 'Fütterung'.

  Regeln für Schlüssel
  --------------------
  * Kurze Einzelwörter (unter 7 Zeichen, ohne Leerzeichen) werden nur ersetzt, wenn sie den
    ganzen Text eines Elements bilden, z. B. 'Alle' oder 'Text'.
  * Längere Schlüssel werden auch innerhalb von Sätzen ersetzt. Der längste Treffer gewinnt.
  * Mit '~' am Anfang erzwingst du das Ersetzen auch bei kurzen Schlüsseln (das ~ wird ignoriert).
  * Emojis am Satzende nicht in den Schlüssel schreiben, sie bleiben automatisch stehen.
*/
window.I18N = {
  languages: { de: 'Deutsch', en: 'English' },
  locale: { de: 'de-DE', en: 'en-GB' },

  /* Deutsch: optionale Überschreibungen der Originaltexte */
  de: {
    // 'Füttern': 'Fütterung',
  },

  en: {
    /* Navigation */
    'Füttern': 'Feed', 'Spucken': 'Vomit', 'Übersicht': 'Overview', 'Einstellungen': 'Settings',
    'Verlauf': 'History', 'Auswertung': 'Analytics', 'Stammdaten': 'Master data', 'Design': 'Design',
    'Fütterungen': 'Feedings', 'Spuck-Ereignisse': 'Vomit incidents',
    'Futter': 'Food', 'Snacks': 'Snacks', 'Getränke': 'Drinks', 'Snack': 'Snack', 'Getränk': 'Drink',
    'Alle': 'All', 'Alle Tiere': 'All animals', 'Abbrechen': 'Cancel', 'Schließen': 'Close', 'Speichern': 'Save',
    'Bearbeiten': 'Edit', 'Anlegen': 'Create', 'Los': 'Go', 'Keine': 'None', 'Unbekannt': 'Unknown',
    'Heute': 'Today', 'Gestern': 'Yesterday', 'heute': 'today', 'Gelöscht': 'Deleted',
    'Hell/Dunkel wechseln': 'Switch light/dark', 'Sprache': 'Language',
    'Tiere ·': 'Animals ·', 'Katze': 'Cat', 'Hund': 'Dog', 'Mahlzeiten': 'Meals', 'Sorte': 'Variety',
    'Hersteller': 'Manufacturer', 'Notiz': 'Note', 'Zeitpunkt': 'Time', 'Text': 'Text',
    'Wasser': 'Water', 'Katzenmilch': 'Cat milk',

    /* Anmeldung & Konto */
    'Anmelden': 'Sign in', 'Willkommen! Administrator anlegen': 'Welcome! Create administrator',
    'Der erste Benutzer wird Administrator. Weitere Benutzer legst du später in den Einstellungen an.': 'The first user becomes the administrator. You can add more users later in the settings.',
    'Dieses Gerät bleibt danach angemeldet.': 'This device stays signed in afterwards.',
    'Benutzername': 'Username', 'Passwort (mind. 8 Zeichen)': 'Password (min. 8 characters)',
    'Konto anlegen': 'Create account', 'Anmeldung fehlgeschlagen': 'Sign-in failed',
    'Name oder Passwort falsch': 'Wrong name or password', 'Nicht angemeldet': 'Not signed in',
    'Konto': 'Account', 'Angemeldet als': 'Signed in as', '(Administrator)': '(administrator)',
    'Abmelden': 'Sign out', 'Neuen Benutzer anlegen': 'Add new user',
    'Benutzer „': 'User “', '“ angelegt': '” created',

    /* Füttern */
    'Wer hat gefressen?': 'Who ate?', 'Welches Futter?': 'Which food?', 'Welcher Snack?': 'Which snack?',
    'Welches Getränk?': 'Which drink?', 'Wie hat’s geschmeckt?': 'How did it taste?',
    'Notiz (optional)': 'Note (optional)', 'z. B. nur halbe Portion': 'e.g. only half a portion',
    'Fütterung speichern': 'Save feeding', 'Name des Herstellers': 'Manufacturer name', 'Name der Sorte': 'Variety name',
    '＋ Neuen Hersteller anlegen …': '+ Add new manufacturer …', '＋ Neue Sorte anlegen …': '+ Add new variety …',
    'Alle Hunde': 'All dogs', 'Alle Katzen': 'All cats', 'Standardgetränk:': 'Default drink:',
    'Immer verfügbar – ein Tipp trägt es für die gewählten Tiere ein.': 'Always available – one tap logs it for the selected animals.',
    'Geben': 'Give', 'Bitte zuerst Tiere auswählen': 'Please select animals first',
    'Rotations-Vorschlag: Was gibt’s heute?': 'Rotation suggestion: what’s for today?',
    'Gut bewertet, verträglich und am längsten nicht im Napf': 'Well rated, well tolerated and longest not in the bowl',
    'Zuletzt eingetragene Fütterungen': 'Recently logged feedings', 'Alle im Verlauf ansehen →': 'View all in history →',
    'Fütterungsrunde bearbeiten': 'Edit feeding round', 'Beteiligte Tiere & Bewertung': 'Animals involved & rating',
    'Fütterung aktualisiert': 'Feeding updated', 'Gelöschte Tiere ausblenden': 'Hide deleted animals',

    /* Spucken */
    'Welche Katze?': 'Which animal?', 'Was wurde erbrochen?': 'What was vomited?', 'Foto & Notiz': 'Photo & note',
    'Foto aufnehmen oder auswählen': 'Take or choose a photo', 'Vorschau': 'Preview',
    'Spuck-Ereignis speichern': 'Save vomit incident', 'futterrelevant': 'food-related',
    'nicht futterrelevant': 'not food-related', 'Ergebnis der Zuordnung': 'Result of the assignment',
    'Nicht futterrelevant – keine Mahlzeiten zugeordnet.': 'Not food-related – no meals assigned.',
    'Gefüttert in den 12 h davor:': 'Fed in the 12 h before:', 'Mahlzeiten in den 12 h davor:': 'Meals in the 12 h before:',
    'Keine Mahlzeit in den 12 h davor gefunden.': 'No meal found in the 12 h before.',
    'Keine Mahlzeit in den 12 h davor.': 'No meal in the 12 h before.',
    'Unverdautes Futter': 'Undigested food', 'Galle / Schaum / Gras': 'Bile / foam / grass',
    'Haarballen': 'Hairballs', 'Sonstiges / Unklar': 'Other / unclear', 'kleiner Fellfreund': 'little furry friend',
    'Noch keine Einträge': 'No entries yet',

    /* Verlauf, Auswertung, Export */
    'Akzeptanz-Matrix (Wer frisst was?)': 'Acceptance matrix (who eats what?)',
    'Durchschnittliche Bewertung pro Tier.': 'Average rating per animal.',
    '= futterrelevantes Spucken binnen 12 h.': '= food-related vomiting within 12 h.',
    'Noch keine Daten.': 'No data yet.', 'Noch keine Daten': 'No data yet', 'Keine Daten.': 'No data.',
    'Unverträglichkeits-Radar': 'Intolerance radar',
    'Was lag in den 12 h vor futterrelevantem Spucken im Napf? Haarballen und Galle/Gras werden herausgefiltert.': 'What was in the bowl in the 12 h before food-related vomiting? Hairballs and bile/grass are filtered out.',
    '× vor Spucken gefüttert': '× fed before vomiting',
    'Bisher wurde keine Sorte vor futterrelevantem Spucken gefunden.': 'So far no variety has been found before food-related vomiting.',
    'Futter-Spucken': 'Food vomiting', 'Ø von': 'Avg. of', 'Das lieben sie am meisten': 'Their favourites',
    'Ranking der Sorten': 'Variety ranking', '× gefüttert': '× fed', '× Spucken binnen 12 h': '× vomiting within 12 h',
    'Alle Daten als CSV oder als druckfertiger Bericht (PDF) der letzten 30 Tage, aufgeschlüsselt nach Tier.': 'All data as CSV or as a print-ready report (PDF) of the last 30 days, broken down by animal.',
    'CSV exportieren': 'Export CSV', 'PDF-Bericht': 'PDF report',

    /* Löschen-Dialoge */
    'Eintrag löschen?': 'Delete entry?', 'Dieser Eintrag wird endgültig gelöscht.': 'This entry will be permanently deleted.',
    'Ja, löschen': 'Yes, delete', 'Katze entfernen?': 'Remove animal?', 'Hersteller löschen?': 'Delete manufacturer?',
    'Sorte löschen?': 'Delete variety?', 'Kategorie löschen?': 'Delete category?',
    '“ wird aus der Auswahl entfernt. Die Historie bleibt erhalten.': '” is removed from the selection. The history is kept.',
    '“ und alle': '” and all', 'zugehörigen Sorten werden aus der Auswahl gelöscht.': 'associated varieties will be removed from the selection.',
    '“ wird aus der Auswahl gelöscht.': '” will be removed from the selection.',
    '“ wird aus der Auswahl entfernt. Bestehende Einträge behalten ihren Namen.': '” will be removed from the selection. Existing entries keep their name.',
    '~„': '“',

    /* Stammdaten */
    'Eigenschaften': 'Properties', 'Alle Tiere beim Füttern vorauswählen': 'Preselect all animals when feeding',
    'Standardgetränk': 'Default drink',
    'Tippe auf den Avatar, um zwischen Katze und Hund zu wechseln. Mit ▲▼ änderst du die Reihenfolge – sie gilt überall. Umbenennen ändert auch die Historie, Löschen entfernt nur aus der Auswahl.': 'Tap the avatar to switch between cat and dog. Use ▲▼ to change the order – it applies everywhere. Renaming also changes the history, deleting only removes from the selection.',
    'Tierart wechseln (Katze/Hund)': 'Switch species (cat/dog)', 'Farbe des Avatars': 'Avatar colour',
    'Nach oben': 'Move up', 'Nach unten': 'Move down', 'Neues Tier …': 'New animal …',
    'Hersteller & Sorten': 'Manufacturers & varieties', 'Neuer Hersteller …': 'New manufacturer …',
    'Neue Sorte …': 'New variety …', 'Auf- oder zuklappen': 'Expand / collapse',
    'Bewertungsstufen': 'Rating levels', '＋ Stufe hinzufügen': '+ Add level', 'Oberste Stufe entfernen': 'Remove top level',
    'Oben = beste Bewertung (': 'Top = best rating (', '), unten = schlechteste (1).': '), bottom = worst (1).',
    'Neue Stufe': 'New level', 'Maximal 7 Stufen': 'Maximum 7 levels', 'Diese Stufe wird noch verwendet': 'This level is still in use',
    'Spuck-Kategorien': 'Vomit categories', 'Neue Kategorie …': 'New category …',
    'Schalter an = futterrelevant (zählt für die 12-h-Zuordnung).': 'Switch on = food-related (counts for the 12 h assignment).',
    'Kategorie angelegt': 'Category created',

    /* Design */
    'Farben': 'Colours', 'Du bearbeitest gerade den': 'You are currently editing', 'Dunkelmodus': 'dark mode',
    'Hellmodus': 'light mode', 'Beide Modi haben getrennte Farben.': 'Both modes have separate colours.',
    'Hintergrund': 'Background', 'Karten': 'Cards', 'Zweittext': 'Secondary text', 'Akzent / Buttons': 'Accent / buttons',
    'Text auf Akzent': 'Text on accent', 'Linien & Rahmen': 'Lines & borders',
    'Header-Verlauf Start': 'Header gradient start', 'Header-Verlauf Ende': 'Header gradient end',
    'Bewertung gut': 'Rating good', 'Bewertung okay': 'Rating okay', 'Bewertung schlecht / Warnung': 'Rating bad / warning',
    'Schrift': 'Typeface', 'Überschriften': 'Headings', 'Fließtext': 'Body text', 'Schriftgröße': 'Font size',
    'Design zurücksetzen': 'Reset design', 'Design zurückgesetzt': 'Design reset',
    'Header-Tier': 'Header animal',
    'Wähle ein oder mehrere Tiere. Beim Öffnen wechselt die App zufällig zwischen ihnen.': 'Choose one or more animals. The app picks one at random each time it opens.',
    '1. Katze': '1. Cat', '2. Hund': '2. Dog', 'Ohne Tier': 'No animal',
    'Cremefarben': 'Cream', 'Schwarz': 'Black', 'Grau getigert': 'Grey tabby',
    'Grau mit weißer Schnauze': 'Grey with white muzzle', 'Spotted Tabby (Braun)': 'Spotted tabby (brown)',
    'Hund Golden': 'Dog golden', 'Hund Schwarz-Weiß': 'Dog black & white', 'Hund Schokobraun': 'Dog chocolate brown',
    'Hund Grau-Weiß': 'Dog grey & white',
    'Morgens': 'Morning', 'Tagsüber': 'Daytime', 'Abends': 'Evening', 'Nachts': 'Night',
    'Sprache der Oberfläche und der Exporte.': 'Language of the interface and exports.',
    'Logo- & Statusleistenfarbe': 'Logo & status bar colour',
    'Farbe der Statusleiste der App. Das App-Icon und die Startfarbe stammen aus der manifest.json.': 'Colour of the app’s status bar. The app icon and splash colour come from manifest.json.',

    /* Begrüßungen */
    'Guten Morgen!': 'Good morning!', 'Moin, Frühaufsteher!': 'Morning, early bird!', 'Frühstückszeit?': 'Breakfast time?',
    'Ein neuer Tag, ein neuer Napf.': 'A new day, a new bowl.', 'Na, schon wach? Die Fellnasen sind es bestimmt.': 'Already up? The furry ones surely are.',
    'Guten Morgen – Kaffee und Katzen?': 'Good morning – coffee and cats?',
    'Hallo, schön dich zu sehen!': 'Hello, nice to see you!', 'Mahlzeit!': 'Bon appétit!', 'Na, wie läuft’s?': 'How’s it going?',
    'Mittagspause mit Fellnasen?': 'Lunch break with the furry ones?', 'Schön, dass du vorbeischaust.': 'Nice that you dropped by.',
    'Hallo zusammen!': 'Hello everyone!', 'Guten Abend!': 'Good evening!', 'Schön, dass du da bist.': 'Nice that you’re here.',
    'Zeit für den Abendnapf?': 'Time for the evening bowl?', 'Feierabend – und die Fellnasen haben Hunger.': 'Off work – and the furry ones are hungry.',
    'Gemütlicher Abend mit den Samtpfoten?': 'Cosy evening with the velvet paws?', 'Na, wie war der Tag?': 'So, how was your day?',
    'Noch wach?': 'Still awake?', 'Nachtschicht bei den Fellnasen': 'Night shift with the furry ones',
    'Schlaf gut – bis später!': 'Sleep well – see you later!', 'Die Nacht gehört den Katzen.': 'The night belongs to the cats.',
    'Späte Runde? Die Katzen schlafen sicher schon.': 'Late round? The cats are surely asleep already.',
    'Mitternachtssnack gefällig?': 'Midnight snack?',

    /* Zeile unter der Begrüßung */
    'Letztes Spucken:': 'Last vomiting:', '– wir behalten es im Blick': '– we’re keeping an eye on it',
    'Beobachtungsmodus: ': 'Observation mode: ', 'Kleine Erinnerung:': 'Small reminder:',
    '– achte auf die nächsten Mahlzeiten': '– watch the next meals',
    'Heute noch keine Mahlzeit erfasst': 'No meal logged today yet', 'Der Napf wartet – noch kein Eintrag für heute': 'The bowl is waiting – no entry for today yet',
    'Heute noch nichts eingetragen – alle schon gefüttert?': 'Nothing logged today – everyone fed already?',
    'Noch leer hier: Wer hat heute schon gefressen?': 'Still empty here: who has eaten today?',
    'Zuletzt hat’s allen geschmeckt': 'Last time everyone enjoyed it', 'Letzte Mahlzeit: Volltreffer bei allen': 'Last meal: bullseye for everyone',
    'Alle zufrieden bei der letzten Runde': 'Everyone happy at the last round', 'Leere Teller bei der letzten Mahlzeit': 'Empty plates at the last meal',
    'Beim letzten Mal hat nicht jeder aufgegessen': 'Not everyone finished last time',
    'Letzte Mahlzeit: mindestens ein Napf blieb voll': 'Last meal: at least one bowl stayed full',
    'Nicht alles kam an – vielleicht hilft eine neue Sorte': 'Not everything landed – maybe a new variety helps',
    '— euer Futter-Tagebuch': '— your food diary', '– alles im Blick': '– everything in view', 'Willkommen zurück bei': 'Welcome back to',

    /* Rückmeldungen (Pop-ups) */
    'Alle haben’s geliebt': 'Everyone loved it', 'hat’s geliebt': 'loved it', 'Teller leer bei': 'Empty plate for',
    '– bessere Kritik gibt’s nicht': '– no better review', 'Leere Teller überall – Volltreffer!': 'Empty plates everywhere – bullseye!',
    'Fünf Sterne von der ganzen Bande': 'Five stars from the whole gang',
    'Heute war wohl nicht ihr Tag … notiert': 'Not their day, it seems … noted',
    'Alles verweigert – gut, dass du’s festhältst': 'Everything refused – good that you keep track',
    'Nicht jeder war begeistert – gut, dass du’s notiert hast': 'Not everyone was thrilled – good that you noted it',
    'Notiert. Vielleicht klappt’s mit einer anderen Sorte': 'Noted. Maybe another variety will work',
    'Gespeichert – gut, dass du so aufpasst': 'Saved – great that you pay such good attention',
    'Eingetragen. Danke, dass du dich kümmerst': 'Logged. Thanks for caring',
    'Notiert! Du kennst deine Fellnasen echt gut': 'Noted! You really know your furry friends',
    'Notiert. Ich habe die letzten Mahlzeiten für dich verknüpft': 'Noted. I linked the recent meals for you',
    'Notiert. Keine Mahlzeit in den 12 h davor gefunden': 'Noted. No meal found in the 12 h before',
    'Notiert. Meist harmlos, gut beobachtet': 'Noted. Usually harmless, well observed',
    'Notiert – gut, dass du hinschaust': 'Noted – good that you pay attention',
    'Gute Besserung,': 'Get well soon,', '– die Mahlzeiten der letzten 12 h sind verknüpft': '– the meals of the last 12 h are linked',
    'Haarballen gehören manchmal dazu – gute Besserung,': 'Hairballs happen – get well soon,',
    'Das war': 'That was', '× in 7 Tagen bei': '× in 7 days for', '– sprich ggf. mit deiner Tierarztpraxis': '– maybe talk to your vet',
    'Gut hydriert – notiert': 'Well hydrated – noted',
    'Willkommen,': 'Welcome,', 'gehört jetzt zur Bande': 'is now part of the gang', 'Neues Familienmitglied:': 'New family member:',
    'ist aus der Auswahl raus – die Erinnerungen bleiben': 'is out of the selection – the memories stay',
    'wurde ausgeblendet. Die Historie bleibt erhalten.': 'was hidden. The history is kept.',
    'ist jetzt ein Hund': 'is now a dog', 'ist jetzt eine Katze': 'is now a cat',
    'Umbenannt – das passt zu': 'Renamed – that suits', 'Neuer Name gespeichert': 'New name saved', 'Umbenannt': 'Renamed',
    'Name leer oder schon vergeben': 'Name empty or already taken',
    'Neue Sorte angelegt – viel Erfolg am Napf': 'New variety created – good luck at the bowl',
    'Sorte hinzugefügt. Hoffentlich ein Hit': 'Variety added. Hopefully a hit',
    'Neuer Hersteller im Regal': 'New manufacturer on the shelf',
    'Hersteller angelegt – jetzt noch eine Sorte dazu': 'Manufacturer created – now add a variety',
    'Hersteller angelegt – jetzt fehlen nur noch die Sorten': 'Manufacturer created – now only the varieties are missing',
    'Hersteller angelegt': 'Manufacturer created', 'Gespeichert': 'Saved',

    /* Gesundheitsdaten */
    'Spuck-Ereignis bearbeiten': 'Edit vomit incident', 'Spuck-Ereignis aktualisiert': 'Vomit incident updated',
    'Foto entfernen': 'Remove photo', 'Foto ersetzen': 'Replace photo', 'Foto': 'Photo', 'Tier': 'Animal', 'Art': 'Type',
    'Gesundheit': 'Health', 'Gesundheitsdaten': 'Health data', 'Steckbrief': 'Profile', 'Geburtstag': 'Birthday',
    'Alter:': 'Age:', 'Noch kein Geburtstag eingetragen.': 'No birthday entered yet.', 'Noch keine Werte.': 'No values yet.',
    'Wert': 'Value', 'Eintragen': 'Log', 'Neues Feld hinzufügen': 'Add new field',
    'Name, z. B. Puls': 'Name, e.g. pulse', 'Einheit': 'Unit', 'Feld hinzufügen': 'Add field',
    'Bitte einen Wert eingeben': 'Please enter a value', 'Wert gespeichert': 'Value saved', 'Feld angelegt': 'Field created',
    'Wert löschen?': 'Delete value?', 'Dieser Messwert wird endgültig gelöscht.': 'This measurement will be permanently deleted.',
    'Feld löschen?': 'Delete field?',
    '“ wird ausgeblendet. Bereits erfasste Werte bleiben gespeichert.': '” will be hidden. Values already recorded are kept.',
    'Größe': 'Height', 'Gewicht': 'Weight', 'Temperatur': 'Temperature',

    /* Erinnerungen (Push) */
    'Erinnerungen': 'Reminders', 'Erinnerungen aktivieren': 'Enable reminders', 'Testnachricht senden': 'Send test message',
    'Deaktivieren': 'Disable', 'Erinnerungen aktiviert': 'Reminders enabled', 'Erinnerungen deaktiviert': 'Reminders disabled',
    'Aktivierung fehlgeschlagen': 'Activation failed', 'Benachrichtigungen wurden nicht erlaubt': 'Notifications were not allowed',
    'Testnachricht gesendet': 'Test message sent', 'Keine Nachricht gesendet': 'No message sent',
    'Benachrichtigungen funktionieren nur über HTTPS und in der installierten App (iPhone: „Zum Home-Bildschirm“, ab iOS 16.4).': 'Notifications only work over HTTPS and in the installed app (iPhone: “Add to Home Screen”, iOS 16.4 or later).',
    'Der Server hat noch keine Push-Unterstützung. Installiere im Container das Paket „pywebpush“.': 'The server has no push support yet. Install the “pywebpush” package in the container.',
    'Erinnerung ca. 2 Stunden nach den üblichen Fütterungszeiten, falls bis dahin kein Futter eingetragen wurde (Snacks und Getränke zählen nicht).': 'Reminder about 2 hours after the usual feeding times if no food has been logged by then (snacks and drinks do not count).',
    'Erkannte Zeiten:': 'Detected times:',
    'Noch keine Fütterungszeiten erkannt (mindestens 3 Tage Daten nötig).': 'No feeding times detected yet (at least 3 days of data needed).'
  },

  /* Sätze mit wechselnden Teilen: [Muster (RegExp), Ersatz]  – $1, $2 … = gefundene Teile */
  rx: {
    en: [
      ['Bei (.+?) gab es (.+?) ein Spuck-Ereignis – bleib aufmerksam', 'For $1 there was a vomiting incident $2 – stay alert'],
      ['Beobachtungsmodus: (.+?) hat (.+?) gespuckt', 'Observation mode: $1 vomited $2'],
      ['Für (.+?): ein Tagebuch mit Liebe', 'For $1: a diary made with love'],
      ['Frisches (.+?) eingetragen', 'Fresh $1 logged'],
      ['vor (\\d+) d', '$1 d ago'],
      ['Zum (.+?) wechseln', 'Switch to $1'],
      ['Alle \\((\\d+)\\)', 'All ($1)'],
      ['· Futter ·', '· Food ·'],
      ['· Getränk ·', '· Drink ·'],
      ['^Futter · ', 'Food · '],
      ['^Getränk · ', 'Drink · '],
      ['Heute,', 'Today,'],
      ['Gestern,', 'Yesterday,'],
      ['\\b(\\d+) Jahre\\b', '$1 years'], ['\\b1 Jahr\\b', '1 year'],
      ['\\b(\\d+) Monate\\b', '$1 months'], ['\\b1 Monat\\b', '1 month'],
      ['\\b(\\d+) Tage\\b', '$1 days'], ['\\b1 Tag\\b', '1 day']
    ]
  }
};
