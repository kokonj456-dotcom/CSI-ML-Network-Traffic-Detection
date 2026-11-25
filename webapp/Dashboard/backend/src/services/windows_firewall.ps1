$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$request = [Console]::In.ReadToEnd() | ConvertFrom-Json
$group = 'Flowwatch'
$store = 'PersistentStore'

function Get-FlowwatchRules {
    @(Get-NetFirewallRule -PolicyStore $store -Group $group -ErrorAction SilentlyContinue |
        Where-Object Name -Match '^Flowwatch-[a-f0-9]{32}$')
}

function Read-FlowwatchRules {
    foreach ($rule in Get-FlowwatchRules) {
        try { $record = $rule.Description | ConvertFrom-Json } catch { continue }
        if ($null -eq $record -or $record.id -ne $rule.Name.Substring(10)) { continue }
        $record | Add-Member -NotePropertyName enabled -NotePropertyValue ($rule.Enabled -eq 'True')
        $record
    }
}

function Find-Rule([string]$id) {
    if ($id -notmatch '^[a-f0-9]{32}$') { throw 'Invalid rule ID.' }
    $rule = Get-FlowwatchRules | Where-Object Name -EQ "Flowwatch-$id" | Select-Object -First 1
    if (!$rule) { throw 'Flowwatch rule not found.' }
    $rule
}

switch ($request.action) {
    'list' {
        $isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
            [Security.Principal.WindowsBuiltInRole]::Administrator)
        @{ writable = $isAdmin; rules = @(Read-FlowwatchRules | Sort-Object createdAt -Descending) } |
            ConvertTo-Json -Depth 5 -Compress
    }
    'add' {
        $existing = @(Read-FlowwatchRules)
        $created = @()
        try {
            foreach ($record in $request.rules) {
                if ($existing | Where-Object { $_.enabled -and $_.ip -eq $record.ip }) {
                    throw 'An enabled Flowwatch rule already exists for this IP.'
                }
                $name = "Flowwatch-$($record.id)"
                New-NetFirewallRule -PolicyStore $store -Name $name -DisplayName "Flowwatch block $($record.ip)" `
                    -Group $group -Description ($record | ConvertTo-Json -Depth 5 -Compress) `
                    -Direction Inbound -Action Block -RemoteAddress $record.ip -Profile Any -Enabled True | Out-Null
                $created += $name
                if (!(Get-NetFirewallRule -PolicyStore ActiveStore -Name $name -ErrorAction SilentlyContinue)) {
                    throw 'The rule was not applied by Windows Firewall policy.'
                }
            }
        } catch {
            foreach ($name in $created) {
                Remove-NetFirewallRule -PolicyStore $store -Name $name -ErrorAction SilentlyContinue
            }
            throw
        }
        @{ ok = $true } | ConvertTo-Json -Compress
    }
    'edit' {
        $rule = Find-Rule $request.id
        if ($rule.Enabled -ne 'True') { throw 'Rule is no longer enabled.' }
        $record = $rule.Description | ConvertFrom-Json
        $record.reason = $request.reason
        $record.expiresAt = $request.expiresAt
        Set-NetFirewallRule -PolicyStore $store -Name $rule.Name -Description ($record | ConvertTo-Json -Compress) | Out-Null
        @{ ok = $true } | ConvertTo-Json -Compress
    }
    'unblock' {
        $rule = Find-Rule $request.id
        $record = $rule.Description | ConvertFrom-Json
        $record.unblockedAt = $request.now
        Set-NetFirewallRule -PolicyStore $store -Name $rule.Name -Enabled False `
            -Description ($record | ConvertTo-Json -Compress) | Out-Null
        @{ ok = $true } | ConvertTo-Json -Compress
    }
    'expire' {
        foreach ($record in Read-FlowwatchRules) {
            if ($record.enabled -and $record.expiresAt -le $request.now) {
                Set-NetFirewallRule -PolicyStore $store -Name "Flowwatch-$($record.id)" -Enabled False | Out-Null
            }
        }
        @{ ok = $true } | ConvertTo-Json -Compress
    }
}
