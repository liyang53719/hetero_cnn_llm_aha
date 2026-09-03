ThisBuild / scalaVersion := "2.13.16"
ThisBuild / organization := "org.heteronpu"
ThisBuild / version := "3.0.0"

lazy val root = (project in file("."))
  .settings(
    name := "heteronpu-three-model-operator-primitives",
    libraryDependencies ++= Seq(
      "org.chipsalliance" %% "chisel" % "6.7.0",
      "edu.berkeley.cs" %% "chiseltest" % "6.0.0" % Test,
      "org.scalatest" %% "scalatest" % "3.2.19" % Test
    ),
    addCompilerPlugin(
      "org.chipsalliance" % "chisel-plugin" % "6.7.0" cross CrossVersion.full
    ),
    scalacOptions ++= Seq("-deprecation", "-feature", "-unchecked"),
    Test / parallelExecution := false
  )
