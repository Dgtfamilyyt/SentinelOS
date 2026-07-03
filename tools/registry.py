from tools.filesystem.current_directory import CurrentDirectoryTool
from tools.filesystem.list_files import ListFilesTool
from tools.filesystem.read_file import ReadFileTool
from tools.filesystem.create_folder import CreateFolderTool


TOOLS = {
    CurrentDirectoryTool.name: CurrentDirectoryTool(),
    ListFilesTool.name: ListFilesTool(),
    ReadFileTool.name: ReadFileTool(),
    CreateFolderTool.name: CreateFolderTool(),
}