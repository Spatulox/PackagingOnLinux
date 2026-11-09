import subprocess
import re

def get_dependencies(binary_path):
    """
    Analyse les dépendances d'un binaire en utilisant ldd et dpkg.
    Exclut les bibliothèques communes.
    
    :param binary_path: Chemin du binaire à analyser
    :return: Ensemble des paquets nécessaires pour le binaire
    """
    try:
        # Exécute la commande ldd pour obtenir les bibliothèques dynamiques utilisées
        ldd_output = subprocess.check_output(['ldd', binary_path]).decode('utf-8')
        
        # Utilise une expression régulière pour extraire les chemins des bibliothèques
        libs = re.findall(r'=> (/lib/.*?|/usr/lib/.*?) \(', ldd_output)
        
        dependencies = set()
        
        # Liste des bibliothèques communes à exclure (peut être étendue selon vos besoins)
        debian_common_libs = set([
            'libc6', 'libgcc-s1', 'libstdc++6', 'libexpat1', 'libcap2',
            'zlib1g', 'libcom-err2', 'libpcre3', 'libkeyutils1',
            'libdbus-1-3', 'libbz2-1.0', 'libgpg-error0',
            'libselinux1', 'liblzma5', 'libcap-ng0', 'libaudit1'
        ])
        fedora_common_lib = set([
            'glibc', 'libgcc', 'libstdc++', 'expat',
            'libcap', 'zlib', 'libcom_err', 'pcre',
            'keyutils-libs,' 'dbus-libs', 'bzip2-libs',
            'libgpg-error', 'libselinux', 'xz-libs',
            'libcap-ng', 'audit-libs'

        ])
        
        # Parcourt les bibliothèques trouvées par ldd
        for lib in libs:
            try:
                # Utilise dpkg -S pour trouver le paquet correspondant à la bibliothèque
                pkg_output = subprocess.check_output(['dpkg', '-S', lib]).decode('utf-8')
                package = pkg_output.split(':')[0]
                
                if package not in debian_common_libs and package not in fedora_common_lib:
                    dependencies.add(package)
            except subprocess.CalledProcessError:
                pass
        
        return dependencies
    
    except FileNotFoundError:
        print(f"Erreur : Le fichier '{binary_path}' n'existe pas ou ldd n'est pas disponible.")
        return set()

# Utilisation du script
if __name__ == "__main__":
    binary_path = input("Entrez le chemin du binaire à analyser : ").strip()
    
    deps = get_dependencies(binary_path)
    
    if deps:
        print("\nDépendances suggérées :")
        print(", ".join(deps))
    else:
        print("\nAucune dépendance spécifique trouvée ou erreur lors de l'analyse.")
