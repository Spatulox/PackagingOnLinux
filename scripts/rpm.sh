#!/bin/bash

# Variables
scriptDir="$(cd "$(dirname "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
projectDir="$(dirname "$scriptDir")"
programName="MyGesClient"
packageVersion="1.0"
architecture="x86_64"  # Changé de "noarch" à "x86_64" car Wails produit des binaires spécifiques à l'architecture
buildDir="$projectDir/builds"
rpmBuildDir="$HOME/rpmbuild"

# Préparation des répertoires RPM
mkdir -p $rpmBuildDir/{BUILD,RPMS,SOURCES,SPECS,SRPMS}

# Copier les fichiers sources
cp "$projectDir/$programName" "$rpmBuildDir/SOURCES/"
cp "$projectDir/icons/appicon.png" "$rpmBuildDir/SOURCES/$programName.png"

# Créer le fichier .spec
cat <<EOF > "$rpmBuildDir/SPECS/$programName.spec"
Name: $programName
Version: $packageVersion
Release: 1%{?dist}
Summary: MyGes Native Desktop for RPM-based systems
License: Proprietary
URL: http://example.com
Source0: %{name}
Source1: %{name}.png

BuildArch: $architecture
Requires: gtk3, webkit2gtk3

%description
MyGes Native Desktop application

%prep
# Pas d'étape de préparation nécessaire pour un binaire précompilé

%install
mkdir -p %{buildroot}/usr/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/%{name}
install -m 755 %{SOURCE0} %{buildroot}/usr/bin/%{name}
install -m 644 %{SOURCE1} %{buildroot}/usr/share/icons/%{name}/%{name}.png

cat <<EOT > %{buildroot}/usr/share/applications/%{name}.desktop
[Desktop Entry]
Name=%{name}
Exec=/usr/bin/%{name}
Icon=/usr/share/icons/%{name}/%{name}.png
Type=Application
Categories=Utility;
EOT

%files
/usr/bin/%{name}
/usr/share/applications/%{name}.desktop
/usr/share/icons/%{name}/%{name}.png

%post
/usr/bin/update-desktop-database &> /dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons &> /dev/null || :

%postun
/usr/bin/update-desktop-database &> /dev/null || :
/usr/bin/gtk-update-icon-cache %{_datadir}/icons &> /dev/null || :

EOF

# Construire le paquet RPM
rpmbuild -bb "$rpmBuildDir/SPECS/$programName.spec"

# Déplacer le RPM construit vers le répertoire de build
mkdir -p "$buildDir"
mv "$rpmBuildDir/RPMS/$architecture/${programName}-${packageVersion}-1."*.rpm "$buildDir/"

echo "Paquet RPM créé : $buildDir/${programName}-${packageVersion}-1."*.rpm