import datetime
import json
from typing import Annotated, Any, Generator, Optional

from dify_easy.model import (
    BasePlugin,
    Credential,
    CredentialType,
    FormType,
    MetaInfo,
    Param,
    ParamType,
    provider,
    tool,
)
from pydantic import BaseModel
from pymstodo import Task, TaskList, ToDoConnection
from pymstodo.client import Token


class MSTodoCredentials(BaseModel):
    token: Annotated[
        str,
        Credential(
            name="token",
            label="Token",
            help="Your Microsoft To Do Token",
            placeholder="Enter your Microsoft To Do Token",
            url="https://learn.microsoft.com/en-us/graph/api/todo-list-tasks?view=graph-rest-1.0&tabs=http",
            type=CredentialType.secret_input,
            required=True,
        ),
    ] = ""


class MSTodoPlugin(BasePlugin):
    credentials: MSTodoCredentials = MSTodoCredentials()

    @provider
    def verify(self):
        pass

    @tool(
        name="get_tasks",
        label="Get Tasks",
        description="Get all tasks from the Microsoft To Do list",
    )
    def get_tasks(self) -> Generator:

        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        lists = [
            {
                "list_id": task_list.list_id,
                "display_name": task_list.displayName,
                "is_owner": task_list.isOwner,
                "is_shared": task_list.isShared,
                "link": task_list.link,
            }
            for task_list in todo_client.get_lists()
        ]

        yield lists
        yield str(lists)

    @tool(
        name="get_list_by_id",
        label="Get List By Id",
        description="Get a list by id from the Microsoft To Do list",
    )
    def get_list_by_id(
        self,
        list_id: Annotated[
            str,
            Param(
                name="list_id",
                label="List Id",
                description="The id of the list to get",
                llm_description="The id of the list to get, type is string",
                type=ParamType.string,
                required=True,
            ),
        ] = "",
    ) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        list = todo_client.get_list(list_id)

        list = {
            "list_id": list.list_id,
            "display_name": list.displayName,
            "is_owner": list.isOwner,
            "is_shared": list.isShared,
            "link": list.link,
        }

        yield list
        yield str(list)

    @tool(
        name="get_all_tasks",
        label="Get All Tasks",
        description="Get all tasks from the Microsoft To Do list",
    )
    def get_all_tasks(self) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        tasks: list[Task] = []
        for _list in todo_client.get_lists():
            tasks.extend(todo_client.get_tasks(_list.list_id))

        _tasks = [
            {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status,
                "body_text": task.body_text if task.body_text else "",
                "due_date": str(task.due_date) if task.due_date else "",
                "created_date": str(task.created_date) if task.created_date else "",
            }
            for task in tasks
        ]

        yield _tasks
        yield str(_tasks)

    @tool(
        name="get_tasks_by_list_id",
        label="Get Tasks By List Id",
        description="Get all tasks from the Microsoft To Do list by list id",
    )
    def get_tasks_by_list_id(
        self,
        list_id: Annotated[
            str,
            Param(
                name="list_id",
                label="List Id",
                description="The id of the list to get",
                llm_description="The id of the list to get, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
    ) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        tasks: list[Task] = todo_client.get_tasks(list_id)

        _tasks = [
            {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status,
                "body_text": task.body_text if task.body_text else "",
                "due_date": str(task.due_date) if task.due_date else "",
                "created_date": str(task.created_date) if task.created_date else "",
            }
            for task in tasks
        ]

        yield _tasks
        yield str(_tasks)

    @tool(
        name="get_task_by_id",
        label="Get Task By Id",
        description="Get a task by id from the Microsoft To Do list",
    )
    def get_task_by_id(
        self,
        task_id: Annotated[
            str,
            Param(
                name="task_id",
                label="Task Id",
                description="The id of the task to get",
                llm_description="The id of the task to get, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
        list_id: Annotated[
            str,
            Param(
                name="list_id",
                label="List Id",
                description="The id of the list to get",
                llm_description="The id of the list to get, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
    ) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        task = todo_client.get_task(task_id, list_id)

        task = {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "body_text": task.body_text if task.body_text else "",
            "due_date": str(task.due_date) if task.due_date else "",
            "created_date": str(task.created_date) if task.created_date else "",
        }

        yield task
        yield str(task)

    @tool(
        name="create_task",
        label="Create Task",
        description="Create a task in the Microsoft To Do list",
    )
    def create_task(
        self,
        list_id: Annotated[
            str,
            Param(
                name="list_id",
                label="List Id",
                description="The id of the list to create the task in",
                llm_description="The id of the list to create the task in, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
        title: Annotated[
            str,
            Param(
                name="title",
                label="Title",
                description="The title of the task to create",
                llm_description="The title of the task to create, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
        due_date: Annotated[
            str,
            Param(
                name="due_date",
                label="Due Date",
                description="The due date of the task to create",
                llm_description="The due date of the task to create, type is string, format is YYYY-MM-DD",
                type=ParamType.string,
                required=False,
            ),
        ],
        body_text: Annotated[
            str,
            Param(
                name="body_text",
                label="Body Text",
                description="The body text of the task to create",
                llm_description="The body text of the task to create, type is string",
                type=ParamType.string,
                required=False,
            ),
        ],
    ) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        task = todo_client.create_task(
            list_id=list_id,
            title=title,
            due_date=(
                datetime.datetime.strptime(due_date, "%Y-%m-%d") if due_date else None
            ),
            body_text=body_text,
        )

        task = {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "due_date": str(task.due_date) if task.due_date else "",
            "created_date": str(task.created_date),
            "body_text": task.body_text if task.body_text else "",
        }

        yield task
        yield str(task)

    @tool(
        name="complete_task",
        label="Complete Task",
        description="Complete a task in the Microsoft To Do list",
    )
    def complete_task(
        self,
        task_id: Annotated[
            str,
            Param(
                name="task_id",
                label="Task Id",
                description="The id of the task to complete",
                llm_description="The id of the task to complete, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
        list_id: Annotated[
            str,
            Param(
                name="list_id",
                label="List Id",
                description="The id of the list the task belongs to",
                llm_description="The id of the list the task belongs to, type is string",
                type=ParamType.string,
                required=True,
            ),
        ],
    ) -> Generator:
        token: Token = Token(**json.loads(self.credentials.token))
        todo_client = ToDoConnection(client_id="", client_secret="", token=token)

        task = todo_client.complete_task(task_id=task_id, list_id=list_id)

        task = {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "due_date": str(task.due_date) if task.due_date else "",
            "created_date": str(task.created_date) if task.created_date else "",
            "body_text": task.body_text if task.body_text else "",
        }

        yield task
        yield str(task)


plugin = MSTodoPlugin(
    meta=MetaInfo(
        name="microsoft_todo",
        label="Microsoft To Do",
        description="A plugin to interact with Microsoft To Do",
        version="0.0.1",
        author="langgenius",
        icon="icon.png",
    ),
)
