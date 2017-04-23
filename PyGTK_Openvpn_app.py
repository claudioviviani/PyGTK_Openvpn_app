#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
# Termino lo script se viene eseguito con Python 3.x
if (sys.version_info > (3, 0)):
    print('Python 3 detected')
    print('Run this script with Python 2.x !')
    sys.exit()

import pygtk
pygtk.require('2.0')
import gtk
import os
import tempfile
import time
import uuid
import fnmatch
import subprocess
import gobject
import threading

# Permette di non bloccare la GUI mentre si esegue un thread in background
# tramite Gtk.
gobject.threads_init()

# Inizio classe
class OpenVpnMngr:

    # Modificare il path in maniera appropriata
    openvpnclipath = "/usr/bin/openvpn"
    # Modificare il path in maniera appropriata
    openvpnclidir = "/home/user/openvpn_connections_dir/"
    openvpnconfext = "*.ovpn"
    killedconn = 0
    noauthtoken = ""
    noputauth = ""
    uservpn = ""
    passvpn = ""

    ##################################################################################
    # Questa funzione serve a nascondere la finestra nel systray invece che chiuderla.
    def hideondel_event(self, widget, event, data=None):
        self.window.hide_on_delete()
        return True


    ##################################################################
    # Questa funzione serve a mostrare a video la finestra principale.
    def status_clicked(self,status):
        # Mostra la finestra principale
        self.window.show()


    ##################################################################
    # Questa funzione esegue l'update della progressbar
    def updatepbar(self):
        new_val = self.progressbar.get_fraction() + 0.01
        if new_val > 1.0:
            new_val = 0.0
        self.progressbar.set_fraction(new_val)
        return self.pbaractivity # True = repeat, False = stop


    #################################################################################
    # Questa funzione crea un file temporaneo con le credenziali di accesso della vpn
    def CreateAuthFile(self, fileuser, filepass):
        file_descriptor, file_path = tempfile.mkstemp(suffix='.tmp')
        open_file = os.fdopen(file_descriptor, 'w')
        open_file.write(fileuser+'\n'+filepass)
        open_file.close()
        return file_path


    #############################################################################
    # Questa funzione crea una finestra di dialogo che permette all'utente finale
    # di inserire graficamente il nome utente e la password della vpn.
    # Tali credenziali verranno passare alla funzione CreateAuthFile.
    def UserPassManager(self, parent, chckb):

        dialog = gtk.MessageDialog(parent,
                              gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
                              gtk.MESSAGE_QUESTION,
                              gtk.BUTTONS_OK_CANCEL,
                              None)
        dialog.format_secondary_markup('<b>OpenVPN Authentication:</b>')
        entrypass = gtk.Entry()
        entrypass.set_visibility(False)
        entryuser = gtk.Entry()
        hboxuser = gtk.HBox()
        hboxuser.pack_start(gtk.Label("User:"), False, 5, 5)
        hboxuser.pack_end(entryuser)
        hboxpass = gtk.HBox()
        hboxpass.pack_start(gtk.Label("Pass:"), False, 5, 5)
        hboxpass.pack_end(entrypass)
        dialog.vbox.pack_end(hboxpass, True, True, 2)
        dialog.vbox.pack_end(hboxuser, True, True, 2)

        dialog.show_all()
        entrypass.connect('activate', lambda _: dialog.response(gtk.RESPONSE_OK))
        entryuser.connect('activate', lambda _: dialog.response(gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)

        r = dialog.run()
        epass= entrypass.get_text().decode('utf8')
        euser = entryuser.get_text().decode('utf8')
        dialog.destroy()

        if r == gtk.RESPONSE_OK:
            self.uservpn = euser
            self.passvpn = epass
            self.entryactivity = False
        else:
            self.noputauth = self.noauthtoken
            self.entryactivity = False


    ######################################################################
    # Questa funzione serve ad eseguire o stoppare una connessione openvpn
    # cliccando sui CheckButtons.
    def StartStopConn(self, widget, data=None, data2=None, data3=None):

        # Se abilito il checkbox....
        if widget.get_active():
            # Genero un token da utilizzare nel caso in cui l'utente annulli la connessione
            # tramite credenziali.
            self.noauthtoken = uuid.uuid4().hex
            # Creo il Thread della connessione
            self.myconn = threading.Thread(target=self.OpenVpnConn, args=(data2, data, data3))
            # Eseguo la connessione
            self.myconn.start()

        # Se disablito il checkbox
        else:
            for ovpnprocess in self.CheckOpenvpnProc():
                if data in str(ovpnprocess[-1:]):
                    subprocess.Popen(['kill', '-9', ovpnprocess[1]])
                    self.killedconn = 1
                    self.pbaractivity = False
                    # Resetto la progressbar
                    self.progressbar.set_fraction(0.0)
                    self.progressbar.set_text("Connection Terminated")


    ###########################################################
    # Funzione che si occupa di gestire la connessione openvpn.
    def OpenVpnConn(self, dirconf, dirfile, chckb):

        # Se esiste l'opzione "auth-user-pass" all'interno del file di configuazione ovpn richiedo l'autenticazione
        if "auth-user-pass" in open(dirfile).read():
            # Per richiedere nome utente e password richiamo la funzione self.UserPassManager.
            # Utilizzo gobject.idle_add per eseguire la funzione sul thread Gtk principale.
            gobject.idle_add(self.UserPassManager, self.window, chckb)
            # Eseguo un loop fino a quando l'utente non inserisce nome utente e password
            while True:
                if self.uservpn != "" and self.passvpn != "":
                    # Creo un file temporaneo per l'autenticazione ed esco dal ciclo
                    fileauth = self.CreateAuthFile(self.uservpn, self.passvpn)
                    # Eseguo openvpn client passando un file di autenticazione
                    ovpnconnection = subprocess.Popen([self.openvpnclipath, '--cd', dirconf, '--config', dirfile, '--auth-user-pass', fileauth],
                                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                    break
                # Se l'utente preme il tasto "annulla" durante l'inserimento dell'username e password
                # deseleziono il checkbox ed annullo la connessione (esco dal ciclo.)
                if self.noputauth == self.noauthtoken:
                    chckb.set_active(False)
                    break
                # A beneficio della CPU
                time.sleep(0.2)
        # Se invece NON esiste l'opzione "auth-user-pass" all'interno del file di configuazione ovpn
        # eseguo la connessione tramite certificati
        else:
            # Eseguo openvpn client senza autenticazione (solo certificati)
            ovpnconnection = subprocess.Popen([self.openvpnclipath, '--cd', dirconf, '--config', dirfile],
                                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        # Parso l'output della connessione openvpn ed eseguo le varie operazioni sugli oggetti GTK solo
        # nel caso in cui l'utente NON ha annullato la connessione.
        if self.noputauth != self.noauthtoken:
            # Creo il processo della process bar
            gobject.timeout_add(100, self.updatepbar)
            # Disabilito il checkbox delle connessioni durante l'esecuzione di un'altra
            for buttonbox in self.chckbuttonlist:
                if chckb != buttonbox:
                    buttonbox.set_sensitive(False)

            # Avvio della ProgressBar
            self.pbaractivity = True
            # Resetto la progressbar
            self.progressbar.set_fraction(0.0)
            self.progressbar.set_text("Connecting...")
            #
            # Dato che il processo openvpn non va in backround dopo che la connessione viene stabilita,
            # creo un loop di 500 cicli inserendoci l'output del programma.
            # Se trovo la stringa "Connection Established" esco dal ciclo, in caso di errore il client
            # interrompe il processo e quindi esce dal ciclo.
            rowvpncounter = 0
            rowvpnmax = 500
            while ( rowvpncounter < rowvpnmax):

                line = ovpnconnection.stdout.readline().rstrip()

                if not line:
                    break

                if "Initialization Sequence Completed" in line:
                    rowvpncounter = rowvpnmax
                    break

                rowvpncounter = rowvpncounter + 1
                # Togliere il commento sottostante solo per avere il debug della connessione sul terminale
                #print line
                # A beneficio della CPU
                time.sleep(0.2)

            if rowvpncounter == rowvpnmax:

                # Stop della ProgressBar
                self.pbaractivity = False
                self.progressbar.set_fraction(0.0)
                self.progressbar.set_text("Connection Established")
                # Togliere il commento sottostante solo per avere il debug della connessione sul terminale
                #print('Connessione OK')

            else:

                # Stop della ProgressBar
                self.pbaractivity = False
                # Resetto la progressbar
                self.progressbar.set_fraction(0.0)
                if self.killedconn == 0:
                    self.progressbar.set_text("Connection Error!")
                else:
                    self.progressbar.set_text("Connection Terminated")
                    # Resetto la variabile per la prossima connessione
                    self.killedconn = 0
                # Se la connessione non va a buon fine, tolgo il flag dal checkbox
                chckb.set_active(False)
                # Togliere il commento sottostante solo per avere il debug della connessione sul terminale
                #print('Connessione KO')

            # Riabilito le checkbox alla fine dell'esecuzione di una connessione vpn
            for buttonbox in self.chckbuttonlist:
                buttonbox.set_sensitive(True)

            # Se esiste la variabile "fileauth", elimino il file temporaneo per l'autenticazione
            if "fileauth" in locals():
                os.unlink(fileauth)
        else:
            self.progressbar.set_text("")

    ###############################################################################
    # Questa funzione serve a controllare se tra i processi del sistema ci sono gia
    # connessioni openvpn atttive.
    def CheckOpenvpnProc(self):
        processlistraw = []
        ps = subprocess.Popen(['ps', '-ef'], stdout=subprocess.PIPE).communicate()[0]
        processes = ps.split('\n')
        nfields = len(processes[0].split()) - 1
        for row in processes[1:]:
            processlistraw.append(row.split(None, nfields))

        return processlistraw


    ###########################################################################################
    # Questa funzione controlla se è stato settato correttamente il path del binario di openvpn
    def CheckOpenvpnBin(self, openvpnbin):

        if os.path.isfile(openvpnbin):
            return True


    ################################################################################
    # Questa funzione controlla se è stato settato correttamente il path contentente
    # i file di configurazione di openvpn (*.ovpn)
    def CheckOpenvpnDir(self, openvpndir):

        if os.path.isdir(openvpndir):
            return True


    #######################################################################
    # Questa funzione serve a fare una scansione ricorsiva di una directory
    # e trovare tutti i file con estensione ".ovpn".
    def OvpnFileList(self):

        ovpnfilename = []

        for root, dirnames, filenames in os.walk(self.openvpnclidir):
            for filename in fnmatch.filter(filenames, self.openvpnconfext):

                ovpnfilename.append( filename+'#####'+os.path.dirname(os.path.abspath(os.path.join(root, filename)))+'#####'+os.path.join(root, filename) )

        return ovpnfilename


    ##############################################
    # Funzione principale della classe OpenVpnMngr
    def __init__(self):
        # Creo una nuova finestra
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)

        # Setto un titolo alla finestra
        self.window.set_title("Openvpn PyGTK Gui")

        # Se viene cliccata la "x" in altro a destra della finestra viene eseguita
        # la funzione self.hideondel_event.
        # Solitamente viene richiamata la funzione gtk.main_quit() per chiudere la finestra,
        # in questo caso viene ridotta nel system tray
        self.window.connect("delete_event", self.hideondel_event)

        # Setto la larghezza dei bordi della finestra
        self.window.set_border_width(20)

        # Creo una vertical box
        vbox = gtk.VBox(True, 2)
        # Inserisco la vertical box nella finestra principale del programma
        self.window.add(vbox)

        # Se non trovo il binario dell'openvpn creo una finestra d'errore
        if not self.CheckOpenvpnBin(self.openvpnclipath):

            errmessage = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
            errmessage.set_markup("Openvpn not found")
            errmessage.set_default_response(gtk.RESPONSE_OK)
            errmessage.run()
            errmessage.destroy()

        # Se non trovo la cartella contenente i file .ovpn creo una finestra d'errore
        if not self.CheckOpenvpnDir(self.openvpnclidir):

            errmessage = gtk.MessageDialog(type=gtk.MESSAGE_ERROR, buttons=gtk.BUTTONS_OK)
            errmessage.set_markup("Openvpn conf dir not found")
            errmessage.run()
            errmessage.destroy()

        # Tramite la funzione OvpnFileList creo una lista contenente tutti i file .ovpn
        connectionlist = self.OvpnFileList()

        # Creo una lista di tutti i CheckButton
        # In questo modo posso gestire e modificare ogni bottone in maniera autonoma (ciclando la lista)
        self.chckbuttonlist = []

        # Ciclo le connessioni vpn in ordine alfabetico (sorted) per creare i CheckButtons
        for vpn in sorted(connectionlist):

            vpnname = vpn.split("#####")[0]
            vpndir  = vpn.split("#####")[1]
            vpnfull = vpn.split("#####")[2]

            # Creo il checkbutton dandogli il nome del file openvpn senza estensione .ovpn
            self.chckbutton = gtk.CheckButton(vpnname[:-5])
            # Inserisco il checkbutton nella lista completa
            self.chckbuttonlist.append(self.chckbutton)

            # Controllo se tra i processi del sistema ci sono gia in esecuzione le vpn
            for ovpnprocess in self.CheckOpenvpnProc():
                # Se trovo una connessione tra i processi setto il checkbutton come attivo
                if vpnfull in str(ovpnprocess[-1:]):
                    self.chckbutton.set_active(True)

            # Se spunto il checkbutton di una vpn, eseguo la funzione StartStopConn
            # così da decidere se far partire o stoppare una connessione openvpn.
            self.chckbutton.connect("toggled", self.StartStopConn, vpnfull, vpndir, self.chckbutton)
            # Inserisco il bottone nella vertical box precedentemente creata
            vbox.pack_start(self.chckbutton, True, True, 2)
            # Mostro il bottone nella GUI.
            self.chckbutton.show()

        # Creo una progressbar
        self.progressbar = gtk.ProgressBar()
        # Inserisco la progressbar sotto i CheckButtons all'interno della vertical box
        vbox.pack_start(self.progressbar, True, True, 2)
        # Mostro la progressbar
        self.progressbar.show()
        # Creo il bottone Quit
        button = gtk.Button("Quit")
        # Quando il bottone Quit viene premuto chiudo la finestra principale
        button.connect("clicked", lambda wid: gtk.main_quit())

        # Inserisco il bottone Quit nella vertical box
        vbox.pack_start(button, True, True, 2)
        # Mostro il bottone Quit
        button.show()
        # Mostro la vertical box
        vbox.show()
        # Appena creata la finestra principale la riduco nel system tray.
        self.window.hide_on_delete()
        # Inserisco l'icona della finestra per il system tray.
        self.icon = gtk.status_icon_new_from_stock(gtk.STOCK_CONNECT)
        # Se viene cliccata l'icona del system tray esegui la funzione self.status_clicked
        self.icon.connect('activate', self.status_clicked )


# Questa funzione crea un main loop della finestra GUI.
# Fino a quando non viene richiamata la funzione gtk.main_quit() tutti i componenti
# della GUI verranno visualizzati.
def main():
    gtk.main()
    return 0


if __name__ == "__main__":
    OpenVpnMngr()
    main()
