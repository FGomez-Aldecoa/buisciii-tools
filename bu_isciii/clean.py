#!/usr/bin/env python

# Generic imports
import sys
import os
import logging
import shutil
from rich.console import Console

# Local imports
import bu_isciii
import bu_isciii.utils
import bu_isciii.drylab_api
import bu_isciii.service_json

log = logging.getLogger(__name__)
stderr = Console(
    stderr=True,
    style="dim",
    highlight=False,
    force_terminal=bu_isciii.utils.rich_force_colors(),
)


class CleanUp:
    def __init__(self, resolution_id=None, path=None, ask_path=False, option=None):
        """
        Description:
            Class to perform the cleaning.

        Usage:

        Attributes:

        Methods:

        """
        # access the api with the resolution name to obtain the data
        # ask away if no input given
        if resolution_id is None:
            self.resolution_id = bu_isciii.utils.prompt_resolution_id()
        else:
            self.resolution_id = resolution_id

        if path is None:
            if ask_path:
                stderr.print("Directory where you want to create the service folder.")
                self.path = bu_isciii.utils.prompt_path(msg="Path")
            else:
                self.path = os.getcwd()
        else:
            self.path = path

        # Obtain info from iskylims api
        conf_api = bu_isciii.config_json.ConfigJson().get_configuration("api_settings")
        rest_api = bu_isciii.drylab_api.RestServiceApi(
            conf_api["server"], conf_api["api_url"]
        )
        self.resolution_info = rest_api.get_request(
            "resolutionFullData", "resolution", self.resolution_id
        )
        self.service_folder = self.resolution_info["Resolutions"][
            "resolutionFullNumber"
        ]
        self.services_requested = self.resolution_info["Resolutions"][
            "availableServices"
        ]
        self.service_samples = self.resolution_info["Samples"]
        if self.service_folder in self.path:
            self.full_path = self.path
        else:
            self.full_path = os.path.join(self.path, self.service_folder)

        # Load service conf
        self.services_to_clean = bu_isciii.utils.get_service_ids(
            self.services_requested
        )
        self.delete_folders = self.get_clean_items(
            self.services_to_clean, type="folders"
        )
        self.delete_files = self.get_clean_items(self.services_to_clean, type="files")
        # self.delete_list = [item for item in self.delete_list if item]
        self.nocopy = self.get_clean_items(self.services_to_clean, type="no_copy")
        self.service_samples = self.resolution_info["Samples"]

        if option is None:
            self.option = bu_isciii.utils.prompt_selection(
                "Options",
                [
                    "full_clean",
                    "rename_nocopy",
                    "clean",
                    "revert_renaming",
                    "show_removable",
                    "show_nocopy",
                ],
            )
        else:
            self.option = option

    def get_clean_items(self, services_ids, type="files"):
        """
        Description:
            Get delete files list from service conf

        Usage:
            object.get_delete_files(services_ids, type = "files")

        Params:
            services_ids [list]: list with services ids selected.
            type [string]: one of these: "files", "folders" or "no_copy" for getting the param from service.json
        """
        service_conf = bu_isciii.service_json.ServiceJson()
        clean_items_list = []
        for service in services_ids:
            try:
                items = service_conf.get_find_deep(service, type)
                if len(clean_items_list) == 0 and len(items) > 0:
                    clean_items_list = items
                elif len(items) > 0:
                    clean_items_list.append(items)
            except KeyError as e:
                stderr.print(
                    "[red]ERROR: Service id %s not found in services json file."
                    % service
                )
                stderr.print("traceback error %s" % e)
                sys.exit()
        if len(clean_items_list) == 0:
            clean_items_list = ""
        return clean_items_list

    def check_path_exists(self):
        # if the folder path is not found, then bye
        if not os.path.exists(self.full_path):
            stderr.print(
                "[red] ERROR: It seems like finding the correct path is beneath me. I apologise. The path: %s does not exitst. Exiting.."
                % self.full_path
            )
            sys.exit()

    def show_removable(self, to_stdout=True):
        """
        Description:
            Print or return the list of objects that must be deleted in this service

        Usage:
            object.show_removable_dirs(to_stdout = [BOOL])

        Params:
            to_stdout [BOOL]: if True, print the list. If False, return the list.
        """
        if to_stdout:
            folders = ", ".join(self.delete_folders)
            stderr.print(f"The following folders will be purge: {folders}")
            files = ", ".join(self.delete_files)
            stderr.print(f"The following files will be deleted: {files}")
            return
        else:
            return self.delete_folders + self.delete_files

    def show_nocopy(self, to_stdout=True):
        """
        Description:
            Print or return the list of objects that must be renamed in this service

        Usage:
            object.show_nocopy(to_stdout = [BOOL])

        Params:
            to_stdout [BOOL]: if True, print the list. If False, return the list.
        """
        if to_stdout:
            no_copy = ", ".join(self.nocopy)
            stderr.print(f"The following files will be renamed with _NC: {no_copy}")
            return
        else:
            return self.nocopy

    def scan_dirs(self, to_find):
        """
        Description:
            Parses the directory tree, and generates two lists:
                -list with the elements (dirs and files) to be deleted
                -list with the dirs to be renamed

        If a list is given as arguments, the names included
        (either files or directories) won't be included in the
        dictionary.

        Usage:
            to_rename, to_delete = object.scan_dirs(to_find=list)

        Params:

        """
        self.check_path_exists()
        pathlist = []
        # key: root, values: [[files inside], [dirs inside]]
        found = []
        # TODO: This has to be revisite if it takes to long.
        # I've tried to continue if found, but I guess there could be several work folders in the project.. Let's see how it goes
        for root, dirs, files in os.walk(self.full_path):
            for item_to_be_found in to_find:
                if root.endswith(item_to_be_found):
                    pathlist.append(root)
                    found.append(item_to_be_found)
                for file in files:
                    path = os.path.join(root, file)
                    if path.endswith(item_to_be_found):
                        pathlist.append(path)
                        found.append(item_to_be_found)

        # Check found list without duplicates
        if not list(dict.fromkeys(found)).sort() == to_find.sort():
            stderr.print(
                "[orange]WARNING:Some files/dir to delete/rename have not been found"
            )
            for item in to_find:
                if item not in found:
                    stderr.print("[orange] %s" % item)
            return pathlist
        else:
            return pathlist

    def find_work(self):
        """
        Description:
            Parses the directory tree to find work folder

        Usage:
            to_delete = object.find_work()

        Params:

        """
        self.check_path_exists()
        workdirs = []
        # key: root, values: [[files inside], [dirs inside]]
        for root, dirs, files in os.walk(self.full_path):
            for name in dirs:
                if name == "work":
                    if os.path.exists(os.path.join(root, name)):
                        workdir = os.path.join(root, name)
                        workdirs.append(workdir)
        return workdirs

    def rename(self, to_find, add, verbose=True):
        """
        Description:
            Rename the files and directories

        Usage:

        Params:

        """
        # generate the list of items to add the "_NC" to
        elements = ", ".join(to_find)
        # ask away if thats ok
        stderr.print(f"The following directories will be renamed: {elements}")
        if not bu_isciii.utils.prompt_yn_question("Is it okay?"):
            stderr.print("You are the boss here.")
            sys.exit()

        path_content = self.scan_dirs(to_find=to_find)

        for directory_to_rename in path_content:
            if add in directory_to_rename:
                stderr.print(
                    "[orange]WARNING: Directory %s already renamed"
                    % directory_to_rename
                )
                continue
            else:
                newpath = directory_to_rename + add
                os.replace(directory_to_rename, newpath)
                if verbose:
                    print(f"Renamed {directory_to_rename} to {newpath}.")
        return

    def rename_nocopy(self, verbose=True):
        """
        Description:

        Usage:

        Params:

        """
        self.rename(to_find=self.nocopy, add="_NC", verbose=verbose)
        return

    def purge_files(self):
        """
        Description:
            Remove the files that must be deleted for the delivery of the service

        Usage:
            object.purge_files()

        Params:

        """
        files_to_delete = []
        for sample_info in self.service_samples:
            for file in self.delete_files:
                file_to_delete = file.replace("sample_name", sample_info["sampleName"])
                files_to_delete.append(file_to_delete)
        path_content = self.scan_dirs(to_find=files_to_delete)
        for file in path_content:
            os.remove(file)
            stderr.print("[green]Successfully removed " + file)
        return

    def purge_folders(self, sacredtexts=["lablog", "logs"], add="", verbose=True):
        """
        Description:
            Remove the files that must be deleted for the delivery of the service
            Their contains, except for the lablog file, and the logs dir, will be
            deleted

        Usage:
            object.purge_folders()

        Params:
            sacredtexts [list]: names (str) of the files that shall not be deleted.

        """
        path_content = self.scan_dirs(to_find=self.delete_folders)

        for directory in path_content:
            # if not empty, and not previously DEL add it to the content
            if not directory.endswith(add):
                for item in os.listdir(directory):
                    if item not in sacredtexts:
                        item_path = os.path.join(directory, item)
                        # shutil if dir, os.remove if file
                        if os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                        else:
                            os.remove(item_path)
                        if verbose:
                            print(f"Removed {item}.")
        return

    def delete_work(self):
        """
        Description:
            Removes full work folder

        Usage:
            object.delete_work()

        Params:

        """
        work_dir = self.find_work()
        if work_dir:
            for work_folder in work_dir:
                shutil.rmtree(work_folder)
        else:
            stderr.print("There is no work folder here")

    def delete_rename(self, verbose=True, sacredtexts=["lablog", "logs"], add="_DEL"):
        """
        Description:
            Remove both files and purge folders defined for the service, and rename to tag.
        Usage:
            object.delete()

        Params:

        """
        # Show removable items
        self.show_removable()

        # Ask for confirmation
        if not bu_isciii.utils.prompt_yn_question("Is it okay?"):
            stderr.print("You got it.")
            sys.exit()

        # Purge folders
        if self.delete_folders != "":
            self.purge_folders(sacredtexts=sacredtexts, add=add, verbose=verbose)
            # Rename to tag.
            self.rename(add=add, to_find=self.delete_folders, verbose=verbose)
        else:
            stderr.print("No folders to remove or rename")
        # Purge work
        self.delete_work()
        # Delete files
        if self.delete_files != "":
            self.purge_files()
        else:
            stderr.print("No files to remove")

    def revert_renaming(self, verbose=True, terminations=["_DEL", "_NC"]):
        """
        Description:
        Reverts the naming (adding of the _NC tag)

        Usage:

        Params:

        """
        to_rename = self.scan_dirs(to_find=terminations)
        if not to_rename:
            stderr.print("[orange] WARNING: I have nothing to revert renaming.")
            return
        for dir_to_rename in to_rename:
            # remove all the terminations
            for term in terminations:
                if dir_to_rename.endswith(term):
                    newname = dir_to_rename.replace(term, "")
                    os.replace(dir_to_rename, newname)
            if verbose:
                print(f"Replaced {dir_to_rename} with {newname}.")

    def full_clean(self):
        """
        Perform and handle the whole cleaning of the service
        """

        self.delete_rename()
        self.rename_nocopy()

    def handle_clean(self):
        """
        Handle clean class options
        """
        if self.option == "show_removable":
            self.show_removable()
        if self.option == "show_nocopy":
            self.show_nocopy()
        if self.option == "full_clean":
            self.full_clean()
        if self.option == "rename_nocopy":
            self.rename_nocopy()
        if self.option == "clean":
            self.delete_rename()
        if self.option == "revert_renaming":
            self.revert_renaming()
