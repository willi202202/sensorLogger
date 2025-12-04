keygenerierung:
cd ~/.ssh/
ssh-keygen -t ed25519 -C "willi202202@raspiroman"
Namen geben Bsp: github_willi202202_key

folgenden public schlüssel bei github eintragen:
cat github_willi202202_key.pub

läuft der ssh agent?:
eval "$(ssh-agent -s)"

privater schlüssel in ssh agent hinzufügen:
ssh-add ~/.ssh/github_willi202202_key

ist der schlüssel eingetragen?
ssh-add -l

klonen:
cd project/
git clone git@github.com:willi202202/sensorLogger.git

Wichtigsten Befehle:
initialisierung:
git init								Erstellt ein neues, leeres Git-Repository im aktuellen Verzeichnis.
git clone <URL>							Lädt ein bestehendes Repository (z.B. von GitHub) in ein lokales Verzeichnis herunter.
git config --global user.name "Name"	Setzt den Benutzernamen, der in allen Commits verwendet wird.
git config --global user.email "E-Mail"	Setzt die E-Mail-Adresse, die in allen Commits verwendet wird.

workflow:
git status					Zeigt den aktuellen Zustand des Repositories: Welche Dateien wurden geändert, welche sind im Staging-Bereich?
git add <Datei>				Verschiebt eine bestimmte geänderte Datei in den Staging-Bereich (bereit für den Commit).
git add .					Verschiebt alle geänderten oder neuen Dateien in den Staging-Bereich.
git commit -m "Nachricht"	Speichert die Dateien aus dem Staging-Bereich dauerhaft in der Historie des Repositories.
git rm --cached <Datei>		Entfernt eine Datei aus dem Staging-Bereich/Repository-Tracking, ohne sie lokal zu löschen.

Branching:
git branch				Listet alle lokalen Branches auf.
git branch <Name>		Erstellt einen neuen Branch mit dem angegebenen Namen.
git checkout <Name>		Wechselt zum angegebenen Branch oder zu einem bestimmten Commit.
git checkout -b <Name>	Erstellt einen neuen Branch und wechselt sofort dorthin (Kombination von branch und checkout).
git merge <Branch>		Fügt die Änderungen vom angegebenen Branch in den aktuellen Branch ein.
git branch -d <Name>	Löscht den angegebenen Branch (nur möglich, wenn er

synchronisierung:
git push		Sendet Ihre lokalen Commits zum Remote-Repository (zum aktuellen Branch).
git pull		Holt Änderungen vom Remote-Repository ab und merged sie sofort in Ihren aktuellen lokalen Branch.
git fetch		Holt Änderungen vom Remote-Repository ab, aber merged sie nicht (erlaubt Ihnen, sie zuerst zu prüfen).
git remote -v	Zeigt die URLs der verbundenen Remote-Repositories an.

hystory, rückgängig machen:
git log						Zeigt die gesamte Commit-Historie an (mit Hash, Autor, Datum).
git log --oneline			Zeigt eine verkürzte, einzeilige Commit-Historie.
git show <Commit-Hash>		Zeigt detaillierte Änderungen eines bestimmten Commits.
git reset <Datei>			Entfernt eine Datei aus dem Staging-Bereich (aber behält lokale Änderungen).
git checkout -- <Datei>		Verwirft lokale Änderungen in einer Datei und stellt die letzte committed Version wieder her. (Achtung: Verlust lokaler Daten!)
git revert <Commit-Hash>	Erstellt einen neuen Commit, der die Änderungen eines vorherigen Commits rückgängig macht (die Historie bleibt erhalten).