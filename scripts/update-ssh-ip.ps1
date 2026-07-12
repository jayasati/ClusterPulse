# Refresh the SSH ingress rule on every clusterpulse-* security group to the
# machine's current public IP.
#
# Consumer connections (CGNAT) rotate public IPs; when SSH to the EC2 nodes
# suddenly times out, run this once and retry. Idempotent: exits without
# changes when the rule already matches.
#
# Usage: .\scripts\update-ssh-ip.ps1 [-AwsProfile clusterpulse] [-Port 22]

param(
    [string]$AwsProfile = "clusterpulse",
    [int]$Port = 22
)

$ErrorActionPreference = "Stop"

$ip = (Invoke-RestMethod -Uri "https://checkip.amazonaws.com").Trim()
$cidr = "$ip/32"
Write-Host "current public IP: $cidr"

$groupIds = (aws ec2 describe-security-groups --profile $AwsProfile `
    --filters "Name=group-name,Values=clusterpulse-*" `
    --query "SecurityGroups[].GroupId" --output text) -split "\s+" | Where-Object { $_ }

if (-not $groupIds) {
    Write-Host "no clusterpulse-* security groups found (profile: $AwsProfile)"
    exit 1
}

foreach ($sg in $groupIds) {
    $existing = (aws ec2 describe-security-groups --profile $AwsProfile --group-ids $sg `
        --query "SecurityGroups[0].IpPermissions[?FromPort==``$Port`` && ToPort==``$Port``].IpRanges[].CidrIp" `
        --output text) -split "\s+" | Where-Object { $_ }

    if ($existing -contains $cidr) {
        Write-Host "${sg}: already allows $cidr - no change"
        continue
    }

    foreach ($old in $existing) {
        aws ec2 revoke-security-group-ingress --profile $AwsProfile --group-id $sg `
            --protocol tcp --port $Port --cidr $old | Out-Null
        Write-Host "${sg}: revoked $old"
    }
    aws ec2 authorize-security-group-ingress --profile $AwsProfile --group-id $sg `
        --protocol tcp --port $Port --cidr $cidr | Out-Null
    Write-Host "${sg}: allowed $cidr"
}

Write-Host "done"
