"""
Simulation inter-process communication module for Flask and simulation script communication.

Communication uses a simple filesystem-based command/response model:
1. Flask writes commands to the commands/ directory.
2. The simulation script polls the commands directory, executes the command, and writes the response to the responses/ directory.
3. Flask polls the responses directory and retrieves the result.
"""

import os
import json
import time
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from ..utils.logger import get_logger

logger = get_logger('fub.simulation_ipc')


class CommandType(str, Enum):
    """Command type"""
    INTERVIEW = "interview"           # Single Agent interview
    BATCH_INTERVIEW = "batch_interview"  # Batch interview
    CLOSE_ENV = "close_env"           # Close environment
    PAUSE = "pause"                   # Pause simulation between rounds
    RESUME = "resume"                 # Resume simulation after pause
    APPLY_INTERVENTION = "apply_intervention"  # Apply intervention to agent during pause


class CommandStatus(str, Enum):
    """Command status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IPCCommand:
    """IPC command"""
    command_id: str
    command_type: CommandType
    args: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "command_type": self.command_type.value,
            "args": self.args,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCCommand':
        return cls(
            command_id=data["command_id"],
            command_type=CommandType(data["command_type"]),
            args=data.get("args", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


@dataclass
class IPCResponse:
    """IPC response"""
    command_id: str
    status: CommandStatus
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "command_id": self.command_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "timestamp": self.timestamp
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'IPCResponse':
        return cls(
            command_id=data["command_id"],
            status=CommandStatus(data["status"]),
            result=data.get("result"),
            error=data.get("error"),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )


class SimulationIPCClient:
    """
    Simulation IPC client for Flask side.

    Used to send commands to the simulation process and wait for responses.
    """
    
    def __init__(self, simulation_dir: str):
        """
        Initialize IPC client
        
        Args:
            simulation_dir: Simulation data directory
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Ensure directories exist
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
    
    def send_command(
        self,
        command_type: CommandType,
        args: Dict[str, Any],
        timeout: float = 60.0,
        poll_interval: float = 0.5
    ) -> IPCResponse:
        """
        Send command and wait for response
        
        Args:
            command_type: Command type
            args: Command arguments
            timeout: Timeout (seconds)
            poll_interval: Poll interval (seconds)
            
        Returns:
            IPCResponse
            
        Raises:
            TimeoutError: Timeout waiting for response
        """
        command_id = str(uuid.uuid4())
        command = IPCCommand(
            command_id=command_id,
            command_type=command_type,
            args=args
        )
        
        # Write command file
        command_file = os.path.join(self.commands_dir, f"{command_id}.json")
        with open(command_file, 'w', encoding='utf-8') as f:
            json.dump(command.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"Send IPC command: {command_type.value}, command_id={command_id}")
        
        # Wait for response
        response_file = os.path.join(self.responses_dir, f"{command_id}.json")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if os.path.exists(response_file):
                try:
                    with open(response_file, 'r', encoding='utf-8') as f:
                        response_data = json.load(f)
                    response = IPCResponse.from_dict(response_data)

                    # Clean up command and response files
                    try:
                        os.remove(command_file)
                        os.remove(response_file)
                    except OSError:
                        pass
                    
                    logger.info(f"Received IPC response: command_id={command_id}, status={response.status.value}")
                    return response
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse response: {e}")
            
            time.sleep(poll_interval)
        
        # Timeout
        logger.error(f"Timeout waiting for IPC response: command_id={command_id}")
        
        # Clean up command file
        try:
            os.remove(command_file)
        except OSError:
            pass
        
        raise TimeoutError(f"Timeout waiting for command response ({timeout} seconds)")
    
    def send_interview(
        self,
        agent_id: int,
        prompt: str,
        platform: str = None,
        timeout: float = 60.0,
        query_context: dict = None
    ) -> IPCResponse:
        """
        Send single Agent interview command
        
        Args:
            agent_id: Agent ID
            prompt: Interview question
            platform: Specify platform (optional)
                - "twitter": only interview Twitter platform
                - "reddit": only interview Reddit platform  
                - None: interview both platforms simultaneously in dual-platform simulations, single platform in single-platform simulations
            timeout: Timeout
            query_context: Optional context with topics and entities for context-aware responses
            
        Returns:
            IPCResponse, result field contains interview result
        """
        args = {
            "agent_id": agent_id,
            "prompt": prompt
        }
        if platform:
            args["platform"] = platform
        if query_context:
            args["query_context"] = query_context
            
        return self.send_command(
            command_type=CommandType.INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_batch_interview(
        self,
        interviews: List[Dict[str, Any]],
        platform: str = None,
        timeout: float = 120.0
    ) -> IPCResponse:
        """
        Send batch interview command
        
        Args:
            interviews: List of interviews, each element contains {"agent_id": int, "prompt": str, "platform": str(optional)}
            platform: Default platform (optional, overridden by each interview item's platform)
                - "twitter": default only interview Twitter platform
                - "reddit": default only interview Reddit platform
                - None: interview each Agent on both platforms simultaneously in dual-platform simulations
            timeout: Timeout
            
        Returns:
            IPCResponse, result field contains all interview results
        """
        args = {"interviews": interviews}
        if platform:
            args["platform"] = platform
            
        return self.send_command(
            command_type=CommandType.BATCH_INTERVIEW,
            args=args,
            timeout=timeout
        )
    
    def send_pause(self, timeout: float = 30.0) -> IPCResponse:
        """Send pause simulation command."""
        return self.send_command(
            command_type=CommandType.PAUSE,
            args={},
            timeout=timeout
        )

    def send_resume(self, timeout: float = 30.0) -> IPCResponse:
        """Send resume simulation command."""
        return self.send_command(
            command_type=CommandType.RESUME,
            args={},
            timeout=timeout
        )

    def send_apply_intervention(
        self,
        agent_id: int,
        intervention_text: str,
        timeout: float = 60.0
    ) -> IPCResponse:
        """Send apply intervention command to running simulation."""
        return self.send_command(
            command_type=CommandType.APPLY_INTERVENTION,
            args={
                "agent_id": agent_id,
                "intervention_text": intervention_text,
            },
            timeout=timeout
        )

    def send_close_env(self, timeout: float = 30.0) -> IPCResponse:
        """
        Send close environment command
        
        Args:
            timeout: Timeout
            
        Returns:
            IPCResponse
        """
        return self.send_command(
            command_type=CommandType.CLOSE_ENV,
            args={},
            timeout=timeout
        )
    
    def check_env_alive(self) -> bool:
        """
        Check if simulation environment is alive
        
        Judge by checking:
        1. env_status.json file exists and status is "alive"
        2. IPC command directory is accessible (process still running)
        """
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        if not os.path.exists(status_file):
            return False
        
        try:
            with open(status_file, 'r', encoding='utf-8') as f:
                status = json.load(f)
            # The sim subprocess reports several "up" states, all of which can
            # accept IPC commands (pause / intervene):
            #   "alive"   — idle / waiting between rounds
            #   "running" — actively processing a round
            #   "paused"  — paused for intervention (the whole point of pausing!)
            # Only a missing file or "stopped"/"closed" means the env is gone.
            if status.get("status") not in ("alive", "running", "paused"):
                return False
        except (json.JSONDecodeError, OSError):
            return False

        # Additional check: verify the commands directory is accessible
        # If process is dead, this directory becomes inaccessible
        commands_dir = os.path.join(self.simulation_dir, "ipc_commands")
        if not os.path.isdir(commands_dir):
            return False
        
        # Check if there's a recent status update (within last 2 minutes)
        # If status is stale, process has exited
        try:
            status_mtime = os.path.getmtime(status_file)
            import time
            if time.time() - status_mtime > 120:  # 2 minutes
                return False
        except OSError:
            pass
        
        return True


class SimulationIPCServer:
    """
    Simulation IPC server for the simulation script side.

    Polls the command directory, executes commands, and returns responses.
    """
    
    def __init__(self, simulation_dir: str):
        """
        Initialize IPC server
        
        Args:
            simulation_dir: Simulation data directory
        """
        self.simulation_dir = simulation_dir
        self.commands_dir = os.path.join(simulation_dir, "ipc_commands")
        self.responses_dir = os.path.join(simulation_dir, "ipc_responses")
        
        # Ensure directories exist
        os.makedirs(self.commands_dir, exist_ok=True)
        os.makedirs(self.responses_dir, exist_ok=True)
        
        # Environment status
        self._running = False
    
    def start(self):
        """Mark server as running"""
        self._running = True
        self._update_env_status("alive")
    
    def stop(self):
        """Mark server as stopped"""
        self._running = False
        self._update_env_status("stopped")
    
    def _update_env_status(self, status: str):
        """Update environment status file"""
        status_file = os.path.join(self.simulation_dir, "env_status.json")
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump({
                "status": status,
                "timestamp": datetime.now().isoformat()
            }, f, ensure_ascii=False, indent=2)
    
    def poll_commands(self) -> Optional[IPCCommand]:
        """
        Poll command directory, return first pending command
        
        Returns:
            IPCCommand or None
        """
        if not os.path.exists(self.commands_dir):
            return None
        
        # Get command files sorted by time
        command_files = []
        for filename in os.listdir(self.commands_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(self.commands_dir, filename)
                command_files.append((filepath, os.path.getmtime(filepath)))
        
        command_files.sort(key=lambda x: x[1])
        
        for filepath, _ in command_files:
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return IPCCommand.from_dict(data)
            except (json.JSONDecodeError, KeyError, OSError) as e:
                logger.warning(f"Failed to read command file: {filepath}, {e}")
                continue
        
        return None
    
    def send_response(self, response: IPCResponse):
        """
        Send response
        
        Args:
            response: IPC response
        """
        response_file = os.path.join(self.responses_dir, f"{response.command_id}.json")
        with open(response_file, 'w', encoding='utf-8') as f:
            json.dump(response.to_dict(), f, ensure_ascii=False, indent=2)
        
        # Delete command file
        command_file = os.path.join(self.commands_dir, f"{response.command_id}.json")
        try:
            os.remove(command_file)
        except OSError:
            pass
    
    def send_success(self, command_id: str, result: Dict[str, Any]):
        """Send success response"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.COMPLETED,
            result=result
        ))
    
    def send_error(self, command_id: str, error: str):
        """Send error response"""
        self.send_response(IPCResponse(
            command_id=command_id,
            status=CommandStatus.FAILED,
            error=error
        ))
