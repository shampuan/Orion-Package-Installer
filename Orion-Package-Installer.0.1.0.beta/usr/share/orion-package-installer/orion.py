#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import apt
import apt.debfile
try:
    import apt_pkg
except ImportError:
    from apt import apt_pkg
from PyQt6.QtWidgets import (QApplication, QMainWindow, QPushButton, QVBoxLayout, QMessageBox,
                             QHBoxLayout, QWidget, QLabel, QTextEdit, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, QProcess, QSize
from PyQt6.QtGui import QPixmap, QIcon
import tempfile
import subprocess

# Linux/Debian tabanlı sistemler için X11 zorlaması
os.environ["QT_QPA_PLATFORM"] = "xcb" # Wayland ortamında sıkıntısız açılması için.

class OrionPackageManager(QMainWindow):
    def __init__(self, deb_path=None):
        super().__init__()
        QApplication.setStyle("Fusion")
        self.setWindowTitle("Orion Package Manager")
        # self.setMinimumSize(600, 500) <-- ilerde duruma bakarım
        self.setFixedSize(600, 550)
        

        # Ana Konteyner
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        self.icons_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
        # Sağ üst köşeye hakkında menüsü koyalım
        self.about_link = QLabel("<a href='#'>Hakkında</a>", self)
        self.about_link.linkActivated.connect(self.show_about_dialog)
        self.about_link.setStyleSheet("margin-right: 15px; margin-top: 10px;")
        self.about_link.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setWindowIcon(QIcon(os.path.join(self.icons_dir, "orionicon.png")))
        
        # --- Üst Bölüm: İkon ve Bilgiler ---
        self.upper_layout = QHBoxLayout()
        
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(96, 96) # 96x96 gayet iyi bir daha buna ellemicem. 
        self.icon_label.setStyleSheet("border: none; background: transparent;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setScaledContents(False) # resmin dengeli ve güzel oturması için
        self.icon_label.setPixmap(QPixmap(os.path.join(self.icons_dir, "orionicon.png")).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        
        self.info_vbox = QVBoxLayout()
        self.name_label = QLabel("<b>Program Adı ve Versiyonu</b>")
        self.desc_label = QLabel("Açıklama / Yorum")
        self.author_label = QLabel("Yapımcı / Adres")
        
        self.info_vbox.addWidget(self.name_label)
        self.info_vbox.addWidget(self.desc_label)
        self.info_vbox.addWidget(self.author_label)
        
        self.upper_layout.addWidget(self.icon_label)
        self.upper_layout.addLayout(self.info_vbox)
        self.layout.addLayout(self.upper_layout)

        # --- Orta Bölüm: Butonlar ---
        self.button_layout = QHBoxLayout()
        self.btn_test = QPushButton(QIcon(os.path.join(self.icons_dir, "analyse.png")), "Analiz Et")
        self.btn_test.clicked.connect(self.run_detailed_analysis)
        self.btn_install = QPushButton(QIcon(os.path.join(self.icons_dir, "install.png")), "Kur")
        self.btn_install.clicked.connect(self.start_installation)
        self.btn_remove = QPushButton(QIcon(os.path.join(self.icons_dir, "uninstall.png")), "Kaldır")
        self.btn_remove.clicked.connect(self.start_uninstallation)
        
        for btn in [self.btn_test, self.btn_install, self.btn_remove]:
            btn.setFixedHeight(40)
            btn.setIconSize(QSize(28, 28)) # İkon boyutu burada büyütülüyor gerekirse tekrar döneriz.
            btn.setStyleSheet("padding-left: 10px; padding-right: 10px; text-align: center;")
            self.button_layout.addWidget(btn)
        
        self.layout.addLayout(self.button_layout)
        
        # Butonlar ile ProgressBar arasındaki küçük boşluk ve durum yazısını buradan ayarlıyoruz
        self.layout.addSpacing(5)
        self.install_status_label = QLabel("")
        self.install_status_label.setStyleSheet("font-size: 11px; color: #0078d4; font-weight: bold;")
        self.install_status_label.setFixedHeight(15)
        self.install_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.addWidget(self.install_status_label)

        # --- İlerleme Çubuğu ve Durum ---
        self.progress = QProgressBar()
        self.progress.setFixedHeight(24)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%p%")
        self.progress.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress.setValue(0)
        self.layout.addWidget(self.progress)

        self.status_label = QLabel("Hazır")
        self.status_label.setStyleSheet("color: #555; font-style: italic;")
        self.layout.addWidget(self.status_label)

        # --- Alt Bölüm: Terminal/Bağımlılık Ekranı ---
        self.layout.addSpacing(10)
        self.terminal_view = QTextEdit()
        self.terminal_view.setReadOnly(True)
        self.terminal_view.setStyleSheet("background-color: #1e1e1e; color: #00ff00; font-family: monospace;")
        self.layout.addWidget(self.terminal_view)

        # Sürükle-bırak desteğini açmak için
        self.setAcceptDrops(True)

        # Geçici dizini her zaman oluştur (dosya sürüklendiğinde lazım olacak)
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_extract_path = self.temp_dir_obj.name

        if deb_path:
            self.analyze_deb(deb_path)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        if files:
            file_path = files[0]
            if file_path.endswith(".deb"):
                self.terminal_view.clear()
                self.analyze_deb(file_path)
            else:
                self.terminal_view.append("HATA: Sadece .deb dosyaları kabul edilir.")

    def analyze_deb(self, path):
        try:
            self.target_file = path # Butonun dosyaya erişebilmesi için yolu kaydet
            self.btn_test.setText("Analiz Et") # Görünümü sıfırlıyoruz
            self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "install.png")))
            self.status_label.setText("Paket analiz ediliyor, lütfen bekleyin...")
            self.install_status_label.setText("İçerik okunuyor...")
            self.icon_label.setPixmap(QPixmap(os.path.join(self.icons_dir, "orionicon.png")).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            QApplication.processEvents()
            
            pkg = apt.debfile.DebPackage(path)
            self.current_pkg_name = pkg.pkgname # Paket adını sakla (çünkü ilerde lazım olacak)
            cache = apt.Cache()
            
            # Bilgileri Bas
            self.name_label.setText(f"<b>{pkg.pkgname}</b> - {pkg._sections.get('Version', '')}")
            self.desc_label.setText(pkg._sections.get('Description', '').split('\n')[0])
            self.author_label.setText(pkg._sections.get('Maintainer', '-'))
            
            # İkon tespiti
            self.get_package_icon(path, pkg.pkgname)
            
            
            # Bağımlılık Analizi
            self.terminal_view.append("--- Bağımlılık Kontrolü ---")
            for dep_list in pkg.depends:
                for dep in dep_list:
                    dep_name = dep[0]
                    if dep_name in cache:
                        self.terminal_view.append(f"✓ {dep_name}")
                    else:
                        self.terminal_view.append(f"<span style='color:red;'>✗ {dep_name} (Bulunamadı!)</span>")
            
            # Kurulu mu ve Versiyon Kontrolü
            if pkg.pkgname in cache and cache[pkg.pkgname].is_installed:
                installed_pkg = cache[pkg.pkgname]
                installed_version = installed_pkg.installed.version
                new_version = pkg._sections.get('Version', '')

                # APT'nin versiyon karşılaştırma algoritması
                
                comparison = apt_pkg.version_compare(new_version, installed_version)

                if comparison > 0:
                    self.btn_install.setText("Yükselt")
                    self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "update.png")))
                    self.install_status_label.setText(f"Yeni versiyon tespit edildi: {new_version}")
                elif comparison < 0:
                    self.btn_install.setText("Sürüm Düşür")
                    self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "downgrade.png")))
                    self.install_status_label.setText(f"Sistemdeki sürüm ({installed_version}) daha güncel.")
                else:
                    self.btn_install.setText("Yeniden Kur")
                    self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "reinstall.png")))
                    self.install_status_label.setText("Aynı sürüm zaten kurulu.")
                
                self.btn_remove.setEnabled(True)
            else:
                # Bu else, 'if pkg.pkgname in cache' bloğuna ait //öğrendiğim iyi oldu sağol YZcim.
                self.btn_install.setText("Kur")
                self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "install.png")))
                self.btn_remove.setEnabled(False)

            self.status_label.setText("Analiz tamamlandı.")

        except Exception as e:
            self.terminal_view.append(f"Hata: {str(e)}")
            self.status_label.setText("Hata oluştu.")

    def get_package_icon(self, pkg_path, pkg_name):
        """Paket içeriğini tarar ve ikonu geçici dizine açar."""
        # Başlangıçta last_found_icon'u genel bir sistem ikonu yap (hiç bulunamazsa diye)
        self.last_found_icon = "package-x-generic"
        
        # 1. Sistem temasında varsa direkt al
        icon = QIcon.fromTheme(pkg_name)
        if not icon.isNull():
            self.icon_label.setText("")
            self.icon_label.setPixmap(icon.pixmap(96, 96))
            self.last_found_icon = pkg_name
            return

        try:
            content = subprocess.check_output(["dpkg-deb", "-c", pkg_path]).decode()
            all_paths = [line.split()[-1] for line in content.splitlines()]
            
            target_icon_path = None
            valid_exts = (".png", ".svg", ".xpm")

            # Pixmaps önceliği
            for p in all_paths:
                if "pixmaps" in p and p.lower().endswith(valid_exts):
                    target_icon_path = p
                    break
            
            # Alternatif: Icons/hicolor
            if not target_icon_path:
                for p in all_paths:
                    if "icons/hicolor" in p and p.lower().endswith(valid_exts):
                        target_icon_path = p
                        if "scalable" in p or "128x128" in p: break

            if target_icon_path:
                clean_path = target_icon_path.lstrip('.')
                # Dosyayı çıkart
                subprocess.run(["dpkg-deb", "--extract", pkg_path, self.temp_extract_path], check=True)
                full_temp_path = os.path.join(self.temp_extract_path, clean_path.lstrip('/'))
                
                if os.path.exists(full_temp_path):
                    pixmap = QPixmap(full_temp_path)
                    if not pixmap.isNull():
                        self.icon_label.setText("")
                        self.icon_label.setPixmap(pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        self.last_found_icon = full_temp_path 
                        return
        except Exception as e:
            print(f"İkon hatası: {e}")

        # Eğer hiçbir şey bulunamazsa label'ı boş bırakıyoruz/onun yerine orion'u koyabiliriz. 
        self.icon_label.setPixmap(QPixmap(os.path.join(self.icons_dir, "orionicon.png")).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.icon_label.setText("")
        
    def closeEvent(self, event):
        """Program kapatıldığında geçici dosyaları temizler."""
        if hasattr(self, 'temp_dir_obj'):
            self.temp_dir_obj.cleanup()
        event.accept()

    def start_installation(self):
        """Paket kurulumunu QProcess ile başlatır (Arayüzü dondurmasın diye yapıyoruz)."""
        if not hasattr(self, 'target_file'):
            self.terminal_view.append("Lütfen önce bir paket seçin.")
            return

        self.install_status_label.setText("Kurulum hazırlanıyor...")
        self.progress.setRange(0, 0)  # Busy mode aktif ediyoruz
        self.terminal_view.clear()
        self.terminal_view.append(f"<b style='color:white;'>Kurulum Başlatıldı: {self.target_file}</b>\n")

        # QProcess nesnesini oluştur
        self.process = QProcess()
        
        # Çıktıları anlık okumak için sinyalleri bağlıyoruz
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.process_finished)

        # Komutu çalıştır (pkexec ile yetki alarak)
        self.process.setProcessEnvironment(self.create_noninteractive_env())
        self.process.start("pkexec", ["apt-get", "install", "-y", "-o", "Dpkg::Progress-Fancy=1", "-o", "APT::Get::Assume-Yes=true", self.target_file])

    def handle_stdout(self):
        """Standart çıktıları terminale basar ve ilerlemeyi takip eder."""
        if not self.process:
            return

        # Veriyi bir kez oku ve değişkene ata
        raw_data = self.process.readAllStandardOutput().data().decode(errors="replace")
        
        # Filtreleme işlemi
        filtered_lines = []
        for line in raw_data.splitlines():
            # Teknik uyarıları filtrele ama kurulum adımlarını geçirme
            if not any(x in line for x in ["debconf:", "dpkg-preconfigure:", "uninitialized frontend"]):
                filtered_lines.append(line)
        
        # Temizlenmiş veriyi terminale bas
        if filtered_lines:
            self.terminal_view.append("\n".join(filtered_lines))

        # İlerleme yüzdesini yakala (Progress: [ 25%]) //bunu iptal edebiliriz.
        if "Progress: [" in raw_data:
            try:
                parts = raw_data.split("Progress: [")[1].split("%")[0].strip()
                if parts.isdigit():
                    percent = int(parts)
                    self.progress.setValue(percent)
            except Exception:
                pass

    def handle_stderr(self):
        """Hata çıktılarını terminale basar."""
        raw_err = self.process.readAllStandardError().data().decode(errors="replace")
        
        # Stdin ve debconf uyarılarını terminale basma, sadece gerçek hataları bas
        if not any(x in raw_err for x in ["stdin", "debconf:", "dpkg-preconfigure:"]):
            self.terminal_view.append(f"<span style='color:#ffaa00;'>{raw_err}</span>")

    def process_finished(self, exit_code, exit_status):
        """İşlem bittiğinde çalışır."""
        if exit_code == 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.install_status_label.setText("Kurulum başarıyla tamamlandı!")
            self.status_label.setText("Bitti.")
            self.terminal_view.append("<b style='color:cyan;'>Sistem bildirimi gönderildi...</b>")
            display_name = getattr(self, 'current_pkg_name', self.target_file)
            self.show_notification("Orion:", f"{display_name} başarıyla kuruldu.")
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.install_status_label.setText("Kurulum başarısız.")
            self.terminal_view.append(f"<b style='color:red;'>İşlem {exit_code} kodu ile durdu.</b>")

    def show_notification(self, title, message):
        """Sistem bildirimi gönderir, varsa ikonu ekler."""
        try:
            # last_found_icon mevcut değilse veya None ise varsayılan ikon kullan
            icon_to_use = getattr(self, 'last_found_icon', None)
            if icon_to_use is None:
                icon_to_use = "package-x-generic" # arşiv ikonuna benzer bir ikon koyduk
            
            # Başındaki noktayı temizle (garantiye alalım)
            if isinstance(icon_to_use, str) and icon_to_use.startswith('.'):
                icon_to_use = icon_to_use.lstrip('.')

            # Bildirimi arka planda gönder (Bloke etmemesi için Popen)
            subprocess.Popen(["notify-send", "-a", "Orion:", "-t", "4000", "-i", str(icon_to_use), title, message])
        except Exception as e:
            print(f"Bildirim gönderilemedi: {e}")        

    def run_detailed_analysis(self):
        """Detaylı analiz ve özet görünümü arasında geçiş yapar."""
        if not hasattr(self, 'target_file') or not self.target_file:
            self.terminal_view.append("Lütfen önce bir paket sürükleyin.")
            return

        # Eğer şu an detaylar görünüyor ise, Bağımlılık Özetine (analyze_deb) geri dön
        if self.btn_test.text() == "Özeti Göster":
            self.terminal_view.clear()
            self.analyze_deb(self.target_file)
            self.btn_test.setText("Analiz Et")
            self.btn_test.setIcon(QIcon(os.path.join(self.icons_dir, "analyse.png")))
            return

        # Detaylı Analiz Kısmı
        self.terminal_view.clear()
        self.btn_test.setText("Özeti Göster") # Buton ismini buradan değiştiriyoruz
        self.btn_test.setIcon(QIcon(os.path.join(self.icons_dir, "analyse.png")))
        self.install_status_label.setText("Paket içeriği listeleniyor...")
        
        self.terminal_view.append("<b style='color:white;'>--- DETAYLI PAKET ANALİZİ ---</b>")
        
        try:
            # 1. Dosya Listesini Al
            self.terminal_view.append("\n<b style='color:#00ff00;'>[ Kurulacak Dosyalar ]</b>")
            files = subprocess.check_output(["dpkg-deb", "-c", self.target_file]).decode()
            clean_files = "\n".join([line.split()[-1] for line in files.splitlines()])
            self.terminal_view.append(clean_files)
            
            # 2. Teknik Detaylar
            self.terminal_view.append("\n<b style='color:yellow;'>[ Teknik Bilgiler ]</b>")
            info = subprocess.check_output(["dpkg-deb", "-I", self.target_file]).decode()
            for line in info.splitlines():
                if any(x in line for x in ["Installed-Size", "Architecture", "Priority", "Section"]):
                    self.terminal_view.append(line.strip())
            
            self.status_label.setText("İçerik görüntülendi.")
            
        except Exception as e:
            self.terminal_view.append(f"\n<span style='color:red;'>Hata: {str(e)}</span>")
            self.btn_test.setText("Analiz Et")
            self.btn_test.setIcon(QIcon(os.path.join(self.icons_dir, "analyse.png")))

    def show_about_dialog(self):
        """Program hakkında bilgilerini gösteren diyalog penceresi. Geliştirince yazısını güncelleyeceğim"""
        about_text = (
            "<h2>Orion Package Manager</h2>"
            "<p><b>Sürüm:</b> 0.1.0 (beta)<br>"
            "<b>Lisans:</b> GNU GPLv3<br>"
            "<b>GUI/UX:</b> Python3-PyQt6<br>"
            "<b>Geliştirici:</b> A. Serhat KILIÇOĞLU (shampuan)<br>"
            "<b>Github:</b> <a href='https://www.github.com/shampuan'>www.github.com/shampuan</a></p>"
            "<hr>"
            "<p>Bu, Debian tabanlı sistemler için geliştirilmiş bir paket kurucusudur.</p>"
            "<p><i>Bu program hiçbir garanti getirmez.</i></p>"
            "<p>Telif hakkı © 2026 - A. Serhat KILIÇOĞLU</p>"
        )
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Orion Hakkında")
        msg.setIconPixmap(QPixmap(os.path.join(self.icons_dir, "orionicon.png")).scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        msg.setText(about_text)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def resizeEvent(self, event):
        """Pencere boyutu değiştikçe Hakkında linkini sağ üstte tutar."""
        self.about_link.move(self.width() - self.about_link.width() - 15, 10)
        super().resizeEvent(event)
    
    def start_uninstallation(self):
        """Yüklü paketi QProcess ile sistemden kaldırır."""
        if not hasattr(self, 'current_pkg_name') or not self.current_pkg_name:
            self.terminal_view.append("Kaldırılacak paket adı bulunamadı.")
            return

        # Kullanıcıya onay soralım (Opsiyonel ama güvenlidir)
        confirm = QMessageBox.question(
            self, "Paket Kaldır", 
            f"'{self.current_pkg_name}' paketini sistemden kaldırmak istediğinize emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if confirm == QMessageBox.StandardButton.No:
            return

        self.btn_remove.setEnabled(False)
        self.btn_install.setEnabled(False)
        self.install_status_label.setText("Paket kaldırılıyor...")
        self.progress.setRange(0, 0)  # Busy mode aktif
        self.terminal_view.clear()
        self.terminal_view.append(f"<b style='color:orange;'>Kaldırma İşlemi Başlatıldı: {self.current_pkg_name}</b>\n")

        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_stdout)
        self.process.readyReadStandardError.connect(self.handle_stderr)
        self.process.finished.connect(self.uninstall_finished)

        # -y parametresi otomatik onay verir ki arada bir de onla uğraşmayalım
        self.process.setProcessEnvironment(self.create_noninteractive_env())
        self.process.start("pkexec", ["apt-get", "remove", "-y", "-o", "Dpkg::Progress-Fancy=1", "-o", "APT::Get::Assume-Yes=true", self.current_pkg_name])

    def uninstall_finished(self, exit_code, exit_status):
        """Kaldırma işlemi bittiğinde çalışır."""
        self.btn_remove.setEnabled(True)
        self.btn_install.setEnabled(True)
        
        if exit_code == 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(100)
            self.install_status_label.setText("Paket başarıyla kaldırıldı.")
            self.status_label.setText("Kaldırıldı.")
            self.show_notification("Orion:", f"{self.current_pkg_name} sistemden kaldırıldı.")
            # Bilgileri tazelemek için analizi tekrar çalıştıralım (Artık 'Kur' butonuna dönecek)
            if hasattr(self, 'target_file'):
                self.analyze_deb(self.target_file)
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)
            self.install_status_label.setText("Kaldırma işlemi başarısız.")
            self.terminal_view.append(f"<b style='color:red;'>Hata Kodu: {exit_code}</b>")

    def create_noninteractive_env(self):
        """APT'nin hem sessiz hem de terminal hataları vermeden çalışmasını sağlar."""
        from PyQt6.QtCore import QProcessEnvironment
        env = QProcessEnvironment.systemEnvironment()
        env.insert("DEBIAN_FRONTEND", "noninteractive")
        env.insert("TERM", "linux") # 'dialog' hatasını önlemek için terminal tipini belirtiyoruz
        env.insert("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin")
        return env

if __name__ == "__main__":
    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    window = OrionPackageManager(path)
    window.show()
    sys.exit(app.exec())
