ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "0.1.0"
val hf = file(sys.env.getOrElse("HARDFLOAT_SOURCE", "../../work/upstream/hardfloat_continuous"))
lazy val root = (project in file(".")).settings(
  name := "heteronpu-continuous-prefill",
  libraryDependencies ++= Seq("org.chipsalliance" %% "chisel" % "6.7.0", "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test, "org.scalatest" %% "scalatest" % "3.2.19" % Test),
  addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full),
  Compile / unmanagedSourceDirectories ++= Seq(hf / "hardfloat/src/main/scala", baseDirectory.value / "../p0_safety/src/main/scala"),
  Compile / unmanagedSources += baseDirectory.value / "../../integration/gemmini/EmitHeteroFP32Alu.scala",
  scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked", "-language:reflectiveCalls"),
  Test / parallelExecution := false
)
