#!/bin/bash

# Test script to verify custom agent web research implementation

echo "Testing Custom Agent Web Research Implementation..."

# Test 1: Check if backend files have been modified correctly
echo "\n1. Checking backend file modifications..."

# Check if research.py has been modified
if grep -q "agent_context" backend/app/api/research.py; then
    echo "✓ backend/app/api/research.py has agent_context parameter"
else
    echo "✗ backend/app/api/research.py missing agent_context parameter"
fi

# Check if deep_research_service.py has been modified
if grep -q "agent_context" backend/app/services/deep_research_service.py; then
    echo "✓ backend/app/services/deep_research_service.py has agent_context parameter"
else
    echo "✗ backend/app/services/deep_research_service.py missing agent_context parameter"
fi

# Check if simulation.py has been modified
if grep -q "agent_context" backend/app/api/simulation.py; then
    echo "✓ backend/app/api/simulation.py has agent_context parameter"
else
    echo "✗ backend/app/api/simulation.py missing agent_context parameter"
fi

# Test 2: Check if frontend files have been modified correctly
echo "\n2. Checking frontend file modifications..."

# Check if Step2EnvSetup.vue has been modified
if grep -q "agentContextForResearch" frontend/src/components/Step2EnvSetup.vue; then
    echo "✓ frontend/src/components/Step2EnvSetup.vue has agent context properties"
else
    echo "✗ frontend/src/components/Step2EnvSetup.vue missing agent context properties"
fi

# Check if simulation.js has been modified
if grep -q "agentContext" frontend/src/api/simulation.js; then
    echo "✓ frontend/src/api/simulation.js has agentContext parameter"
else
    echo "✗ frontend/src/api/simulation.js missing agentContext parameter"
fi

# Test 3: Check if web_research.py has been modified
if grep -q "agent_context" backend/app/skills/fub_web_research/scripts/web_research.py; then
    echo "✓ backend/app/skills/fub_web_research/scripts/web_research.py has agent_context parameter"
else
    echo "✗ backend/app/skills/fub_web_research/scripts/web_research.py missing agent_context parameter"
fi

# Test 4: Check if documentation has been created
if [ -f "CUSTOM_AGENT_WEB_RESEARCH_IMPLEMENTATION.md" ]; then
    echo "✓ Implementation documentation created"
else
    echo "✗ Implementation documentation missing"
fi

# Test 5: Check if there are any syntax errors in Python files
echo "\n3. Checking Python syntax..."

# Check for syntax errors in modified Python files
for file in backend/app/api/research.py backend/app/services/deep_research_service.py backend/app/api/simulation.py; do
    if python -c "import py_compile; py_compile.compile('$file')" 2>/dev/null; then
        echo "✓ $file has valid syntax"
    else
        echo "✗ $file has syntax errors"
    fi
done

echo "\nTest completed!"
