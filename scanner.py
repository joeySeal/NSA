"""
python3 -m venv env
source env/bin/activate
pip install npyscreen
python scanner.py
"""

import os
import glob
import re
import sys
import time

import npyscreen


# This application class serves as a wrapper for the initialization of curses
# and also manages the actual forms of the application
class Datastore(object):
    target = None
    discovered_hosts = []


class MyTestApp(npyscreen.NPSAppManaged):
    scan_form = None

    def onStart(self):
        self.datastore = Datastore()
        self.main_form = self.addForm("MAIN", MainForm, name="Main Form")
        self.diff_form = self.addForm("DIFF", DiffForm, name="Diff Form")
        self.live_form = self.addForm("LIVE", LiveForm, name="Live Form")


# This form class defines the display that will be presented to the user.

class MainForm(npyscreen.Form):
    keypress_timeout_default = 10

    def create(self):
        # get first command line argument using python standard library
        argv = sys.argv
        if len(argv) > 1:
            target = argv[1]
        else:
            target = ""
        self.target = self.add(npyscreen.TitleText, name="Target", value=target)

    def afterEditing(self):
        self.parentApp.datastore.target = self.target.value
        if self.parentApp.scan_form:
            self.parentApp.removeForm('SCAN')
        self.parentApp.scan_form = self.parentApp.addForm("SCAN", ScanForm, name="Scan Form")
        self.parentApp.switchForm('SCAN')


class ScanForm(npyscreen.Form):
    wg_result = None
    wg_scan_again = None
    wg_discovered_hosts = None
    wg_diff = None
    wg_live = None
    filename = None

    def create(self):
        self.wg_result = self.add(npyscreen.MultiLineEdit, name="Result", value="", max_height=3, editable=False)
        self.add_widgets()

    def beforeEditing(self):
        self.name = "Scan Form for " + self.parentApp.datastore.target
        self.DISPLAY()
        self.scan()
        self.DISPLAY()

    def afterEditing(self):
        self.parentApp.switchForm('MAIN')

    def on_scan_again(self):
        self.parentApp.switchForm('SCAN')

    def get_discovered_hosts(self, scan_result):
        result = scan_result.split('\n')
        line: str
        return [line.split(' ')[0] for line in result if line.find('host up') > 0]

    def add_widgets(self):
        self.wg_scan_again = self.add(npyscreen.ButtonPress, name='Scan Again',
                                      when_pressed_function=self.scan)
        self.wg_diff = self.add(npyscreen.ButtonPress, name='Show Diff',
                                when_pressed_function=self.switch_to_diff)
        self.wg_live = self.add(npyscreen.ButtonPress, name='Live',
                                when_pressed_function=self.switch_to_live)
        self.wg_discovered_hosts = self.add(
            npyscreen.TitleMultiSelect,
            max_height=-2, value=[], name="Discovered Hosts",
            values=self.parentApp.datastore.discovered_hosts,
            scroll_exit=True)
        self.DISPLAY()

    def scan(self):
        try:
            target = self.parentApp.datastore.target
            self.wg_result.value = f"Scanning... CTRL-C to stop. {target}"
            self.DISPLAY()
            self.get_new_file_name()
            cmd = f'nmap -sn -n -v {target}'
            result = os.popen(cmd).read()
            result = '\n'.join([line for line in result.split('\n') if
                                line.startswith('Nmap scan report for') or line.startswith('Host is up')])
            result = '\n'.join([re.sub(r' \(\d+\.\d+s latency\)\.', '', line) for line in result.split('\n')])
            result = result.replace("\nHost is up", ' [host up]')
            result = result.replace("Nmap scan report for ", '')
            result = result + '\n'
            self.name = f'Scan Form for {target} - {self.filename}'
            self.wg_result.value = f"Scan complete and saved to {self.filename}"
            self.save_to_file(self.filename, result)
            self.parentApp.datastore.discovered_hosts = self.get_discovered_hosts(result)
            self.wg_discovered_hosts.values = self.parentApp.datastore.discovered_hosts
        except KeyboardInterrupt:
            self.wg_result.value = f"Scan interrupted"
        self.DISPLAY()

    def get_new_file_name(self):
        """Searches for files that are named scan_*.txt and increments the number and returns full file name"""
        files = glob.glob('scan_*.txt')
        if files:
            new_number = max([int(re.search(r'\d+', aFile).group()) for aFile in files]) + 1
            new_file = f'scan_{new_number}.txt'
        else:
            new_file = 'scan_1.txt'
        self.filename = new_file

    def get_previous_filename(self):
        current_number = self.filename.replace('scan_', '').replace('.txt', '')
        previous_number = int(current_number) - 1
        return f"scan_{previous_number}.txt"

    def switch_to_diff(self):
        self.parentApp.diff_form.filename = self.filename
        self.parentApp.switchForm('DIFF')

    def switch_to_live(self):
        selected_hosts = [self.wg_discovered_hosts.values[i] for i in self.wg_discovered_hosts.value]
        self.parentApp.live_form.targets = selected_hosts
        self.parentApp.switchForm('LIVE')

    def show_diff(self):
        cmd = f'diff {self.get_previous_filename()} {self.filename}'
        result = os.popen(cmd).read()
        self.wg_result.value = f"{cmd}\n{result}"
        self.DISPLAY()

    def save_to_file(self, filename, output):
        with open(filename, 'w') as f:
            f.write(output)


class DiffForm(npyscreen.Form):
    filename = None

    def create(self):
        self.wg_result = self.add(npyscreen.MultiLineEdit, name="Result", value="", max_height=3, editable=False)

    def beforeEditing(self):
        self.name = "Difference between " + self.get_previous_filename() + " and " + self.filename
        self.show_diff()
        self.DISPLAY()

    def afterEditing(self):
        self.parentApp.switchForm('SCAN')

    def get_previous_filename(self):
        current_number = self.filename.replace('scan_', '').replace('.txt', '')
        previous_number = int(current_number) - 1
        return f"scan_{previous_number}.txt"

    def show_diff(self):
        cmd = f'diff {self.get_previous_filename()} {self.filename}'
        self.name = cmd
        result = os.popen(cmd).read()
        self.wg_result.value = f"{result}"
        self.DISPLAY()


class LiveForm(npyscreen.Form):
    targets = []
    live_monitor_thread = None

    def create(self):
        self.name = "Live Monitor"
        self.wg_result = self.add(
            npyscreen.TitleMultiSelect,
            name="Monitoring Hosts",
            values=[],
            scroll_exit=True)

    def beforeEditing(self):
        self.name = "Live Monitor"
        self.display()
        self.live_monitor()
        # self.start_live_monitor()

    def afterEditing(self):
        self.parentApp.switchForm('SCAN')

    def live_monitor(self):
        """run nmap -sn -n -v on all targets in `self.targets` in threading, and update the list in self.wg_result"""
        try:
            self.name = "Live Monitor CTRL-C to stop"
            while True:
                values = []
                for target in self.targets:
                    cmd = f'nmap -sn -n -v {target}'
                    result = os.popen(cmd).read()
                    result = '\n'.join([line for line in result.split('\n') if
                                        line.startswith('Nmap scan report for') or line.startswith('Host is up')])
                    result = '\n'.join([re.sub(r' \(\d+\.\d+s latency\)\.', '', line) for line in result.split('\n')])
                    result = result.replace("\nHost is up", ' [host up]')
                    result = result.replace("Nmap scan report for ", '')
                    result = result
                    values.append(result)
                self.wg_result.values = values
                self.DISPLAY()
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        self.name = "Live Monitoring stopped"
        self.DISPLAY()
        self.parentApp.switchForm('SCAN')


if __name__ == '__main__':
    TA = MyTestApp()
    TA.run()
