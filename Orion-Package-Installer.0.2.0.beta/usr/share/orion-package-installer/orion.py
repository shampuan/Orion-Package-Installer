#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import apt
import apt.debfile
import shutil
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

class OrionPackageInstaller(QMainWindow):
    def __init__(self, deb_path=None):
        super().__init__()
        QApplication.setStyle("Fusion")
        self.setWindowTitle("Orion Package Installer v0.2.0.beta")
        # self.setMinimumSize(600, 500) <-- ilerde duruma bakarım
        self.setFixedSize(450, 250) # Yenilendi.
        

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
        self.author_label = QLabel("Yapımcı")
        self.address_label = QLabel("Adres") # Yeni etiket
        
        # Yazı boyutlarını biraz küçülterek daralan pencereye uyum sağlayalım
        self.author_label.setStyleSheet("font-size: 11px;")
        self.address_label.setStyleSheet("font-size: 11px; color: #666;")
        
        self.info_vbox.addWidget(self.name_label)
        self.info_vbox.addWidget(self.desc_label)
        self.info_vbox.addWidget(self.author_label)
        self.info_vbox.addWidget(self.address_label) # Adresi alt satıra ekledik
        
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
        self.terminal_view.hide()  # Başlangıçta gizli tutmak için kullanıyoruz.
        self.layout.setStretch(6, 0)

        # Sürükle-bırak desteğini açmak için
        self.setAcceptDrops(True)

        # Geçici dizini her zaman oluştur (dosya sürüklendiğinde lazım olacak)
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_extract_path = self.temp_dir_obj.name
        self.cached_details = ""

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
            # Her analiz başında geçici dizini temizle ve yeniden oluştur
            if os.path.exists(self.temp_extract_path):
                shutil.rmtree(self.temp_extract_path)
            os.makedirs(self.temp_extract_path)

            # APT Önbelleğini her analiz başında tazele
            cache = apt.Cache()

            self.target_file = path # Butonun dosyaya erişebilmesi için yolu kaydet
            self.btn_test.setText("Analiz Et") # Görünümü sıfırlıyoruz
            self.btn_install.setIcon(QIcon(os.path.join(self.icons_dir, "install.png")))
            self.status_label.setText("Paket analiz ediliyor, lütfen bekleyin...")
            self.install_status_label.setText("İçerik okunuyor...")
            self.icon_label.setPixmap(QPixmap(os.path.join(self.icons_dir, "orionicon.png")).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            QApplication.processEvents()
            
            pkg = apt.debfile.DebPackage(path)
            self.current_pkg_name = pkg.pkgname # Paket adını sakla
            
            # Bilgileri Bas
            self.name_label.setText(f"<b>{pkg.pkgname}</b> - {pkg._sections.get('Version', '')}")
            self.desc_label.setText(pkg._sections.get('Description', '').split('\n')[0])
            maintainer_info = pkg._sections.get('Maintainer', '-')
            if "<" in maintainer_info:
                name, email = maintainer_info.split("<", 1)
                self.author_label.setText(name.strip())
                self.address_label.setText(f"<{email.strip()}")
            else:
                self.author_label.setText(maintainer_info)
                self.address_label.setText("")
            
            # İkon tespiti
            self.get_package_icon(path, pkg.pkgname)
            
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
            # Detayları önceden hazırlıyoruz (Anlık açılması için)
            self.cached_details = "<b style='color:white;'>--- PAKET DETAYLARI VE BAĞIMLILIKLAR ---</b><br>"
            self.cached_details += "<br><b style='color:#00ff00;'>[ Bağımlılıklar ]</b><br>"
            for dep_list in pkg.depends:
                for dep in dep_list:
                    dep_name = dep[0].split(':')[0]
                    if dep_name in cache:
                        status = "✓"
                        color = "white"
                        suffix = ""
                    else:
                        status = "✗"
                        color = "red"
                        suffix = " (depoda bulunamadı)"
                    self.cached_details += f"<span style='color:{color};'>{status} {dep_name}{suffix}</span><br>"

            self.cached_details += "<br><b style='color:yellow;'>[ Kurulacak Dosyalar ]</b><br>"
            files = subprocess.check_output(["dpkg-deb", "-c", path]).decode()
            clean_files = "<br>".join([line.split()[-1] for line in files.splitlines() if not line.endswith("/")])
            self.cached_details += clean_files
            
        except Exception as e:
            self.terminal_view.append(f"Hata: {str(e)}")
            self.status_label.setText("Hata oluştu.")

    def get_package_icon(self, pkg_path, pkg_name):
        """Paket içeriğini tarar, .desktop dosyasından ikon adını bulur ve en kaliteli ikonu ayıklar."""
        self.last_found_icon = os.path.join(self.icons_dir, "orionicon.png")
        self.icon_label.setPixmap(QPixmap(self.last_found_icon).scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

        try:
            # 1. İçeriği Listele ve Paketi Aç
            content = subprocess.check_output(["dpkg-deb", "-c", pkg_path]).decode()
            all_paths = [line.split()[-1] for line in content.splitlines()]
            # subprocess.run(["dpkg-deb", "--extract", pkg_path, self.temp_extract_path], check=True)
            # Tüm paketi açmak yerine sadece dosya listesini zaten 'content' ile aldık.
            # Artık sadece ihtiyacımız olan dosyaları tekil olarak ayıklayacağız.
            
            # 2. .desktop dosyasından ikon ismini çek
            icon_keyword = pkg_name
            has_extension = False
            desktop_file = next((p for p in all_paths if p.lower().endswith(".desktop")), None)
            
            if desktop_file:
                # Sadece .desktop dosyasını ayıkla
                cmd = f'dpkg-deb --fsys-tarfile "{pkg_path}" | tar -xC "{self.temp_extract_path}" "{desktop_file}"'
                subprocess.run(cmd, shell=True, check=True)
                full_desktop_path = os.path.join(self.temp_extract_path, desktop_file.lstrip('./'))
                if os.path.exists(full_desktop_path):
                    with open(full_desktop_path, "r", errors="ignore") as f:
                        for line in f:
                            if line.startswith("Icon="):
                                icon_keyword = line.split("=")[1].strip()
                                # Eğer zaten uzantılıysa (.png .svg gibi), ararken tekrar eklemeyelim
                                if any(icon_keyword.lower().endswith(ex) for ex in [".png", ".svg", ".xpm"]):
                                    has_extension = True
                                else:
                                    has_extension = False
                                break
            
            # 3. Akıllı Arama
            target_icon_path = None
            if icon_keyword.startswith("/"):
                target_icon_path = next((p for p in all_paths if icon_keyword in p), None)

            if not target_icon_path:
                valid_exts = [""] if has_extension else [".svg", ".png", ".xpm"]
                # Hiyerarşi: Scalable -> Çözünürlükler -> Pixmaps
                for ext in valid_exts:
                    search_term = (icon_keyword + ext).lower()
                    for folder in ["scalable", "512x512", "256x256", "128x128", "96x96", "48x48", "pixmaps"]:
                        for p in all_paths:
                            p_low = p.lower()
                            if folder in p_low and search_term in p_low:
                                target_icon_path = p
                                break
                        if target_icon_path: break
                    if target_icon_path: break

            # 4. İkonu Bas
            if target_icon_path:
                # Sadece seçilen ikon dosyasını paket içerisinden ayıkla
                cmd = f'dpkg-deb --fsys-tarfile "{pkg_path}" | tar -xC "{self.temp_extract_path}" "{target_icon_path}"'
                subprocess.run(cmd, shell=True, check=True)
                final_path = os.path.join(self.temp_extract_path, target_icon_path.lstrip('./'))
                if os.path.exists(final_path):
                    pixmap = QPixmap(final_path)
                    if not pixmap.isNull():
                        self.icon_label.setPixmap(pixmap.scaled(96, 96, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        self.last_found_icon = final_path
                        return

        except Exception as e:
            print(f"HATA: {e}")

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
                icon_to_use = os.path.abspath(icon_to_use) if os.path.exists(str(icon_to_use)) else icon_to_use

            # Bildirimi arka planda gönder (Bloke etmemesi için Popen)
            subprocess.Popen(["notify-send", "-a", "Orion:", "-t", "4000", "-i", str(icon_to_use), title, message])
        except Exception as e:
            print(f"Bildirim gönderilemedi: {e}")        

    def run_detailed_analysis(self):
        """Önceden hazırlanan veriyi anında gösterir ve pencereyi büyütür."""
        if not hasattr(self, 'target_file') or not self.target_file:
            self.status_label.setText("Önce bir paket sürükleyin!")
            return

        # Pencere boyutunu ve terminal görünürlüğünü değiştir
        self.toggle_terminal()

        # Terminal açıldıysa, önbellekteki veriyi bas
        if self.terminal_view.isVisible() and hasattr(self, 'cached_details'):
            self.terminal_view.setHtml(self.cached_details)

    def show_about_dialog(self):
        """Program hakkında bilgilerini gösteren diyalog penceresi. Geliştirince yazısını güncelleyeceğim"""
        about_text = (
            "<h2>Orion Package Installer</h2>"
            "<p><b>Sürüm:</b> 0.2.0 (beta)<br>"
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
    
    def closeEvent(self, event):
        """Pencere kapatıldığında çalışan kurulumun bozulmamasını sağlar."""
        if hasattr(self, 'process') and self.process.state() == QProcess.ProcessState.Running:
            # Süreci ana pencereden kopar ki pencere kapansa da apt-get ölmesin
            # Bunu kullanıcı pencereyi kapatırsa kurulum yarım kalmasın diye yaptırıyorum
            # Değilse ortalık garışabilir.
            self.process.setParent(None)
            
            # Kullanıcıya bir bildirim göndererek işlemin arkada sürdüğünü haber verelim
            self.show_notification("Orion:", "Arayüz kapatıldı ancak kurulum arka planda devam ediyor.")
            
        event.accept()
    
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

    def toggle_terminal(self):
        """Pencere boyutunu ve terminal görünürlüğünü yönetir."""
        if self.terminal_view.isVisible():
            self.terminal_view.hide()
            self.setFixedSize(450, 250)
            self.btn_test.setText("Detayları Göster")
        else:
            self.terminal_view.show()
            self.setFixedSize(450, 550)
            self.btn_test.setText("Detayları Gizle")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    path = sys.argv[1] if len(sys.argv) > 1 else None
    window = OrionPackageInstaller(path)
    window.show()
    sys.exit(app.exec())
