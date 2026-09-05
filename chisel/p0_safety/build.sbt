ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "0.1.0"
lazy val root = (project in file(".")).settings(
  name := "heteronpu-p0-safety-chisel",
  libraryDependencies ++= Seq(
    "org.chipsalliance" %% "chisel" % "6.7.0",
    "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test,
    "org.scalatest" %% "scalatest" % "3.2.19" % Test
  ),
  addCompilerPlugin("org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full),
  scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked", "-language:reflectiveCalls"),
  Test / parallelExecution := false
)
