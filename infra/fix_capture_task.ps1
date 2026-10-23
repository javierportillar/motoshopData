# fix_capture_task.ps1
# EJECUTAR COMO ADMINISTRADOR (clic derecho > "Ejecutar como administrador")
# Recrea MotoShop_CaptureNewSales con trigger DIARIO

$taskName = "MotoShop_CaptureNewSales"
$scriptPath = "C:\Users\MotoShop\Documents\javidevmoto\infra\capture_new_sales.ps1"
$taskXml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.3" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>Captura incremental de ventas cada ~2 min durante horario de atencion (17:50-23:50 COL) - DIARIO</Description>
    <URI>\$taskName</URI>
  </RegistrationInfo>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-3015984919-1988592598-2621329-1001</UserId>
      <LogonType>S4U</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT10M</ExecutionTimeLimit>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <StartWhenAvailable>true</StartWhenAvailable>
    <IdleSettings>
      <Duration>PT10M</Duration>
      <WaitTimeout>PT1H</WaitTimeout>
      <StopOnIdleEnd>true</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <UseUnifiedSchedulingEngine>true</UseUnifiedSchedulingEngine>
  </Settings>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-06-11T17:50:00-05:00</StartBoundary>
      <Repetition>
        <Interval>PT2M</Interval>
        <Duration>PT6H</Duration>
        <StopAtDurationEnd>true</StopAtDurationEnd>
      </Repetition>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -WindowStyle Hidden -File $scriptPath</Arguments>
    </Exec>
  </Actions>
</Task>
"@

# Borrar anterior si existe
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "Tarea anterior eliminada"
}

# Crear nueva
Register-ScheduledTask -TaskName $taskName -Xml $taskXml -Force
Write-Host "Tarea $taskName creada: DIARIA 17:50-23:50, cada 2 min"
Write-Host "Estado:" (Get-ScheduledTask -TaskName $taskName).State
